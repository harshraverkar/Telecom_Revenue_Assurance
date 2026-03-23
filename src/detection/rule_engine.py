"""
src/detection/rule_engine.py
----------------------------
Runs all ENABLED leakage detection rules against MySQL.

Steps:
    1. Reads config/leakage_rules.yaml -- finds enabled rules
    2. Calls matching SQL function from sql_rules.py
    3. Writes detected type into cdr.sql_detected_leakage_type in MySQL
    4. Prints accuracy report vs ground_truth_leakage_type

Run:
    python -m src.detection.rule_engine

Team guide -- to add your rule (e.g. L4):
    1. Add detect_L4_duplicates() in sql_rules.py
    2. Add "detect_L4_duplicates": detect_L4_duplicates in ALL_SQL_DETECTORS
    3. Set enabled: true for L4_duplicate in config/leakage_rules.yaml
    4. Run this file again
"""

import yaml
import sys
import pandas as pd
import mysql.connector

from pathlib import Path
from src.detection.sql_rules import ALL_SQL_DETECTORS
from src.utils.config import cfg

RULES_PATH = str(cfg.project_root / "config" / "leakage_rules.yaml")


# -------------------------------------------------------------
# 1. Load enabled rules from YAML
# -------------------------------------------------------------
def load_enabled_rules() -> list:
    with open(RULES_PATH) as f:
        data = yaml.safe_load(f)

    enabled = []
    for key, rule in data.get("rules", {}).items():
        if rule.get("enabled") is True:
            enabled.append({"key": key, **rule})

    print(f"\n[rule_engine] MySQL    : {cfg.mysql_host}:{cfg.mysql_port}"
          f" / {cfg.mysql_database}")
    print(f"[rule_engine] Rules    : {RULES_PATH}")
    print(f"[rule_engine] Enabled  : "
          f"{[r.get('code', r['key']) for r in enabled]}")
    return enabled


# -------------------------------------------------------------
# 2. Run one rule
# -------------------------------------------------------------
def run_rule(rule: dict) -> pd.DataFrame:
    fn_name = rule.get("sql_function", "")
    fn      = ALL_SQL_DETECTORS.get(fn_name)

    if fn is None:
        print(f"\n  [SKIP] {rule['key']} -- "
              f"'{fn_name}' not in ALL_SQL_DETECTORS")
        return pd.DataFrame()

    label = rule.get("code", rule["key"])
    print(f"\n  [{label}] Running {fn_name}()...", end=" ", flush=True)
    df = fn()
    print(f"-> {len(df):,} records flagged")
    return df


# -------------------------------------------------------------
# 3. Write sql_detected_leakage_type to MySQL
# -------------------------------------------------------------
def write_to_mysql(df: pd.DataFrame) -> int:
    if df.empty or "cdr_id" not in df.columns:
        return 0

    leakage_code = df["detected_leakage_type"].iloc[0]
    cdr_ids      = df["cdr_id"].tolist()

    conn = mysql.connector.connect(**cfg.mysql_connection_args())
    cur  = conn.cursor()

    # Update in batches of 1000
    written = 0
    batch_size = 1000
    for i in range(0, len(cdr_ids), batch_size):
        batch = cdr_ids[i : i + batch_size]
        placeholders = ", ".join(["%s"] * len(batch))
        cur.execute(
            f"UPDATE cdr SET sql_detected_leakage_type = %s "
            f"WHERE cdr_id IN ({placeholders})",
            [leakage_code] + batch
        )
        written += cur.rowcount

    conn.commit()
    cur.close()
    conn.close()

    print(f"  -> Wrote sql_detected_leakage_type='{leakage_code}' "
          f"for {written:,} rows in MySQL.")
    return written


# -------------------------------------------------------------
# 4. Accuracy report
# -------------------------------------------------------------
def accuracy_report(rule: dict, df: pd.DataFrame) -> None:
    if df.empty or "cdr_id" not in df.columns:
        return

    leakage_code   = df["detected_leakage_type"].iloc[0]
    detected_count = len(df)

    conn = mysql.connector.connect(**cfg.mysql_connection_args())
    cur  = conn.cursor()

    # True positives -- SQL detected AND ground truth matches
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(charge_expected), 0)
        FROM cdr
        WHERE sql_detected_leakage_type = %s
          AND ground_truth_leakage_type = %s
    """, (leakage_code, leakage_code))
    tp, tp_loss = cur.fetchone()

    # Total actual leakage in ground truth
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(charge_expected), 0)
        FROM cdr
        WHERE ground_truth_leakage_type = %s
    """, (leakage_code,))
    total_actual, total_loss = cur.fetchone()

    cur.close()
    conn.close()

    fp        = detected_count - tp
    precision = tp / detected_count if detected_count > 0 else 0
    recall    = tp / total_actual   if total_actual   > 0 else 0

    print()
    print("=" * 62)
    print(f"  RESULTS -- {rule['key']}")
    print("=" * 62)
    print(f"  Detected by SQL rule  : {detected_count:>10,}")
    print(f"  True positives  (TP)  : {tp:>10,}"
          f"  <- ground_truth = sql_detected")
    print(f"  False positives (FP)  : {fp:>10,}"
          f"  <- sql flagged but not actual leakage")
    print(f"  Ground truth total    : {total_actual:>10,}"
          f"  <- all {leakage_code} in DB")
    print(f"  Precision             : {precision:>10.1%}"
          f"  TP / (TP + FP)")
    print(f"  Recall                : {recall:>10.1%}"
          f"  TP / ground truth total")
    print(f"  Estimated loss (Rs.)    : {float(total_loss):>10,.2f}")
    print("=" * 62)

    # Sample rows
    show = [c for c in [
        "cdr_id", "subscriber_id", "call_type", "start_time",
        "estimated_loss", "detected_leakage_type",
        "ground_truth_leakage_type",
    ] if c in df.columns]
    print(f"\n  First 10 flagged rows:")
    print("  " + df[show].head(10).to_string(index=False).replace("\n", "\n  "))


# -------------------------------------------------------------
# MAIN
# -------------------------------------------------------------
def run() -> None:
    # Test connection
    print("\n[rule_engine] Testing MySQL connection...")
    try:
        conn = mysql.connector.connect(**cfg.mysql_connection_args())
        conn.close()
        print(f"[rule_engine] Connected OK")
    except Exception as e:
        print(f"[rule_engine] MySQL connection FAILED: {e}")
        print("[rule_engine] Check config/config.yaml")
        sys.exit(1)

    # Load rules
    rules = load_enabled_rules()
    if not rules:
        print("\n[rule_engine] No enabled rules found.")
        print("  Open config/leakage_rules.yaml and set enabled: true")
        return

    # Clear previous detections for enabled rules
    conn = mysql.connector.connect(**cfg.mysql_connection_args())
    cur  = conn.cursor()
    for rule in rules:
        code = rule.get("code", rule["key"])
        cur.execute(
            "UPDATE cdr SET sql_detected_leakage_type = '' "
            "WHERE sql_detected_leakage_type = %s", (code,)
        )
    conn.commit()
    cur.close()
    conn.close()

    # Run each rule
    for rule in rules:
        df = run_rule(rule)
        if not df.empty:
            write_to_mysql(df)
        accuracy_report(rule, df)

    print("\n[rule_engine] Done.\n")


if __name__ == "__main__":
    run()
