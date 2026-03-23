"""
scripts/query.py
----------------
Run SQL queries against MySQL telecom_ra database.

Usage:
    python scripts/query.py --run summary
    python scripts/query.py --run l1_results
    python scripts/query.py --run l1_accuracy
    python scripts/query.py --run l1_proof
    python scripts/query.py --run detection_status
    python scripts/query.py --list
    python scripts/query.py --sql "SELECT COUNT(*) FROM cdr"
    python scripts/query.py --run l1_results --export results/l1.csv
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from src.utils.db import run_query
from src.utils.config import cfg


# -- All team queries ------------------------------------------
SAVED_QUERIES = {

    "summary": """
        SELECT 'Total CDRs'               AS metric, COUNT(*) AS value FROM cdr
        UNION ALL
        SELECT 'Leakage (ground truth)',   COUNT(*) FROM cdr
            WHERE ground_truth_leakage_type != 'none'
        UNION ALL
        SELECT 'Clean records',            COUNT(*) FROM cdr
            WHERE ground_truth_leakage_type = 'none'
        UNION ALL
        SELECT 'SQL detected so far',      COUNT(*) FROM cdr
            WHERE sql_detected_leakage_type != ''
    """,

    "row_counts": """
        SELECT 'cdr'                AS tbl, COUNT(*) AS rows FROM cdr
        UNION ALL SELECT 'rating_events',       COUNT(*) FROM rating_events
        UNION ALL SELECT 'mediation_events',    COUNT(*) FROM mediation_events
        UNION ALL SELECT 'billing_records',     COUNT(*) FROM billing_records
        UNION ALL SELECT 'roaming_settlements', COUNT(*) FROM roaming_settlements
        UNION ALL SELECT 'subscribers',         COUNT(*) FROM subscribers
        UNION ALL SELECT 'leakage_audit',       COUNT(*) FROM leakage_audit
        UNION ALL SELECT 'plans',               COUNT(*) FROM plans
        UNION ALL SELECT 'cell_towers',         COUNT(*) FROM cell_towers
    """,

    # L1 queries
    "l1_results": """
        SELECT cdr_id, subscriber_id, call_type, start_time,
               charge_expected, ground_truth_leakage_type,
               sql_detected_leakage_type
        FROM cdr
        WHERE sql_detected_leakage_type = 'L1_unbilled'
        ORDER BY charge_expected DESC
        LIMIT 50
    """,

    "l1_accuracy": """
        SELECT
            ground_truth_leakage_type   AS ground_truth,
            sql_detected_leakage_type   AS sql_detected,
            COUNT(*)                    AS records,
            ROUND(SUM(charge_expected), 2) AS total_loss_inr
        FROM cdr
        WHERE sql_detected_leakage_type = 'L1_unbilled'
           OR ground_truth_leakage_type = 'L1_unbilled'
        GROUP BY 1, 2
        ORDER BY records DESC
    """,

    "l1_proof": """
        SELECT c.cdr_id, c.mediation_status,
               c.ground_truth_leakage_type,
               c.sql_detected_leakage_type,
               r.rating_id
        FROM cdr c
        LEFT JOIN rating_events r ON c.cdr_id = r.rating_id
        WHERE c.sql_detected_leakage_type = 'L1_unbilled'
        LIMIT 10
    """,

    "l1_by_calltype": """
        SELECT call_type,
               COUNT(*) AS count,
               ROUND(SUM(charge_expected), 2) AS total_loss_inr
        FROM cdr
        WHERE sql_detected_leakage_type = 'L1_unbilled'
        GROUP BY call_type
        ORDER BY total_loss_inr DESC
    """,

    "l1_by_month": """
        SELECT LEFT(start_time, 7) AS month,
               COUNT(*) AS l1_count,
               ROUND(SUM(charge_expected), 2) AS total_loss_inr
        FROM cdr
        WHERE sql_detected_leakage_type = 'L1_unbilled'
        GROUP BY month
        ORDER BY month
    """,

    "detection_status": """
        SELECT sql_detected_leakage_type AS detected_as,
               COUNT(*) AS records,
               ROUND(SUM(charge_expected), 2) AS total_loss_inr
        FROM cdr
        GROUP BY sql_detected_leakage_type
        ORDER BY records DESC
    """,

    "ground_truth_distribution": """
        SELECT ground_truth_leakage_type AS leakage_type,
               COUNT(*) AS records,
               ROUND(SUM(charge_expected), 2) AS total_loss_inr
        FROM cdr
        GROUP BY ground_truth_leakage_type
        ORDER BY records DESC
    """,
}


def print_result(df: pd.DataFrame, title: str = "") -> None:
    if title:
        print(f"\n{'-'*60}")
        print(f"  {title}")
        print(f"{'-'*60}")
    if df.empty:
        print("  (no rows returned)")
        return
    try:
        from tabulate import tabulate
        print(tabulate(df, headers="keys", tablefmt="psql",
                       showindex=False, floatfmt=".2f"))
    except ImportError:
        print(df.to_string(index=False))
    print(f"\n  {len(df):,} row(s)  |  "
          f"MySQL: {cfg.mysql_host}/{cfg.mysql_database}")


def run_saved(name: str, export: str = None) -> None:
    if name not in SAVED_QUERIES:
        print(f"  Query '{name}' not found.")
        list_queries()
        return
    df = run_query(SAVED_QUERIES[name])
    print_result(df, title=name)
    if export:
        os.makedirs(os.path.dirname(export) or ".", exist_ok=True)
        df.to_csv(export, index=False)
        print(f"  Exported to: {export}")


def list_queries() -> None:
    print("\n  Available queries:")
    groups = {
        "Overview"    : ["summary", "row_counts"],
        "L1 detection": ["l1_results", "l1_accuracy", "l1_proof",
                         "l1_by_calltype", "l1_by_month"],
        "Status"      : ["detection_status", "ground_truth_distribution"],
    }
    for group, names in groups.items():
        print(f"\n  {group}:")
        for n in names:
            print(f"    python scripts/query.py --run {n}")


def main():
    parser = argparse.ArgumentParser(description="Telecom RA -- MySQL Query Tool")
    parser.add_argument("--run",    type=str, help="Run a saved query by name")
    parser.add_argument("--sql",    type=str, help="Run any SQL string directly")
    parser.add_argument("--export", type=str, help="Export result to CSV path")
    parser.add_argument("--list",   action="store_true", help="List all queries")
    args = parser.parse_args()

    if args.list:
        list_queries()
    elif args.run:
        run_saved(args.run, export=args.export)
    elif args.sql:
        df = run_query(args.sql)
        print_result(df)
        if args.export:
            os.makedirs(os.path.dirname(args.export) or ".", exist_ok=True)
            df.to_csv(args.export, index=False)
            print(f"  Exported to: {args.export}")
    else:
        list_queries()


if __name__ == "__main__":
    main()
