"""
src/data/migrate.py
-------------------
Migrates all tables from SQLite to MySQL.

Run once after generating the SQLite dataset:
    python -m src.data.migrate
    OR
    python scripts/setup.py   (recommended - tests connection first)

What it does:
    1. Connects to MySQL
    2. Creates telecom_ra database
    3. Creates all 9 tables with correct DDL
    4. Copies all rows from SQLite in batches
    5. Prints summary
"""

import sqlite3
import math
import sys
import mysql.connector

from src.utils.config import cfg

# -------------------------------------------------------------
# CREATE TABLE statements
# Columns match EXACTLY what the v2 generator produces.
# Verified against generator.py append() calls.
# -------------------------------------------------------------
CREATE_STATEMENTS = {

    "plans": """
        CREATE TABLE IF NOT EXISTS plans (
            plan_id             VARCHAR(10)  NOT NULL PRIMARY KEY,
            plan_name           VARCHAR(50),
            plan_type           VARCHAR(20),
            monthly_rent        DOUBLE,
            voice_rate_per_min  DOUBLE,
            sms_rate            DOUBLE,
            data_rate_per_mb    DOUBLE,
            roaming_multiplier  DOUBLE,
            free_mins           INT,
            free_sms            INT,
            free_data_mb        DOUBLE,
            valid_from          VARCHAR(20),
            valid_to            VARCHAR(20),
            promo_eligible      INT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "cell_towers": """
        CREATE TABLE IF NOT EXISTS cell_towers (
            tower_id            VARCHAR(10)  NOT NULL PRIMARY KEY,
            region              VARCHAR(20),
            tower_type          VARCHAR(20),
            operator            VARCHAR(10),
            latitude            DOUBLE,
            longitude           DOUBLE,
            capacity_erlangs    INT,
            is_active           INT,
            interconnect_type   VARCHAR(20)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "subscribers": """
        CREATE TABLE IF NOT EXISTS subscribers (
            subscriber_id       VARCHAR(10)  NOT NULL PRIMARY KEY,
            msisdn              VARCHAR(20),
            imsi                VARCHAR(25),
            plan_id             VARCHAR(10),
            region              VARCHAR(20),
            credit_class        VARCHAR(5),
            registration_date   VARCHAR(25),
            is_active           INT,
            customer_type       VARCHAR(20),
            avg_monthly_spend   DOUBLE,
            churn_date          VARCHAR(25),
            last_activity_date  VARCHAR(25),
            device_category     VARCHAR(20),
            linked_account_id   VARCHAR(10),
            subsidy_device_id   VARCHAR(15)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "cdr": """
        CREATE TABLE IF NOT EXISTS cdr (
            cdr_id                       VARCHAR(20)  NOT NULL PRIMARY KEY,
            subscriber_id                VARCHAR(10),
            msisdn_a                     VARCHAR(20),
            msisdn_b                     VARCHAR(20),
            imsi                         VARCHAR(25),
            plan_id                      VARCHAR(10),
            tower_id                     VARCHAR(10),
            region                       VARCHAR(20),
            call_type                    VARCHAR(10),
            start_time                   VARCHAR(25),
            end_time                     VARCHAR(25),
            duration_sec                 INT,
            data_mb                      DOUBLE,
            is_roaming                   INT,
            roaming_country              VARCHAR(30),
            roaming_iso                  VARCHAR(5),
            termination_cause            VARCHAR(20),
            charge_expected              DOUBLE,
            charge_truncated             DOUBLE,
            rounding_loss                DOUBLE,
            ground_truth_leakage_type    VARCHAR(40),
            leakage_type                 VARCHAR(40),
            leakage_flag                 INT,
            sql_detected_leakage_type    VARCHAR(40),
            model_predicted_leakage_type VARCHAR(40),
            model_confidence             DOUBLE,
            mediation_status             VARCHAR(15),
            leakage_metadata             TEXT,
            cli_original                 VARCHAR(20),
            cli_presented                VARCHAR(20),
            route_type                   VARCHAR(20),
            signaling_protocol           VARCHAR(10),
            destination_type             VARCHAR(20),
            number_range_type            VARCHAR(20),
            access_type                  VARCHAR(20),
            pbx_flag                     INT,
            device_type                  VARCHAR(20),
            imei                         VARCHAR(20),
            tethering_flag               INT,
            app_category                 VARCHAR(20),
            INDEX idx_subscriber  (subscriber_id),
            INDEX idx_leakage     (leakage_flag),
            INDEX idx_gt          (ground_truth_leakage_type),
            INDEX idx_sql_det     (sql_detected_leakage_type),
            INDEX idx_call_type   (call_type),
            INDEX idx_start_time  (start_time)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "mediation_events": """
        CREATE TABLE IF NOT EXISTS mediation_events (
            mediation_id      VARCHAR(30)  NOT NULL PRIMARY KEY,
            cdr_id            VARCHAR(20),
            subscriber_id     VARCHAR(10),
            received_at       VARCHAR(25),
            processed_at      VARCHAR(25),
            status            VARCHAR(15),
            error_code        VARCHAR(30),
            output_to_rating  INT,
            processing_node   VARCHAR(10),
            INDEX idx_cdr_id (cdr_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "rating_events": """
        CREATE TABLE IF NOT EXISTS rating_events (
            rating_id       VARCHAR(30)  NOT NULL PRIMARY KEY,
            cdr_id          VARCHAR(20),
            subscriber_id   VARCHAR(10),
            plan_id         VARCHAR(10),
            rated_at        VARCHAR(25),
            call_type       VARCHAR(10),
            billable_units  DOUBLE,
            unit_type       VARCHAR(10),
            rate_applied    DOUBLE,
            charge_amount   DOUBLE,
            discount        DOUBLE,
            final_charge    DOUBLE,
            rounding_loss   DOUBLE,
            leakage_type    VARCHAR(40),
            rating_engine   VARCHAR(10),
            INDEX idx_cdr_id (cdr_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "billing_records": """
        CREATE TABLE IF NOT EXISTS billing_records (
            bill_id          VARCHAR(40)  NOT NULL PRIMARY KEY,
            subscriber_id    VARCHAR(10),
            plan_id          VARCHAR(10),
            bill_month       VARCHAR(7),
            monthly_rent     DOUBLE,
            voice_charge     DOUBLE,
            data_charge      DOUBLE,
            sms_charge       DOUBLE,
            roaming_charge   DOUBLE,
            total_calls      INT,
            total_sms        INT,
            total_data_mb    DOUBLE,
            total_charge     DOUBLE,
            tax_amount       DOUBLE,
            grand_total      DOUBLE,
            bill_status      VARCHAR(15),
            payment_date     VARCHAR(25),
            dispatch_status  VARCHAR(15),
            dispatch_date    VARCHAR(25),
            agent_id         VARCHAR(10),
            INDEX idx_subscriber (subscriber_id),
            INDEX idx_month      (bill_month)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "roaming_settlements": """
        CREATE TABLE IF NOT EXISTS roaming_settlements (
            settlement_id     VARCHAR(30)  NOT NULL PRIMARY KEY,
            cdr_id            VARCHAR(20),
            subscriber_id     VARCHAR(10),
            roaming_country   VARCHAR(30),
            roaming_iso       VARCHAR(5),
            partner_operator  VARCHAR(10),
            call_type         VARCHAR(10),
            duration_sec      INT,
            data_mb           DOUBLE,
            wholesale_rate    DOUBLE,
            settlement_amount DOUBLE,
            settlement_date   VARCHAR(10),
            status            VARCHAR(15),
            tap_file_id       VARCHAR(15),
            tap_seq_number    INT,
            tap_status        VARCHAR(15),
            expected_records  INT,
            received_records  INT,
            INDEX idx_cdr_id (cdr_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "leakage_audit": """
        CREATE TABLE IF NOT EXISTS leakage_audit (
            audit_id                  VARCHAR(40)  NOT NULL PRIMARY KEY,
            cdr_id                    VARCHAR(20),
            leakage_type              VARCHAR(40),
            ground_truth_leakage_type VARCHAR(40),
            leakage_category          VARCHAR(10),
            subscriber_id             VARCHAR(10),
            plan_id                   VARCHAR(10),
            call_type                 VARCHAR(10),
            start_time                VARCHAR(25),
            region                    VARCHAR(20),
            tower_id                  VARCHAR(10),
            estimated_loss            DOUBLE,
            estimated_loss_inr        DOUBLE,
            detection_method          VARCHAR(20),
            auto_detected             INT,
            sql_detected              INT,
            ml_predicted              INT,
            resolved                  INT,
            resolution_note           TEXT,
            severity                  VARCHAR(10),
            INDEX idx_leakage_type (leakage_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
}

TABLE_ORDER = [
    "plans", "cell_towers", "subscribers",
    "cdr", "mediation_events", "rating_events",
    "billing_records", "roaming_settlements", "leakage_audit"
]

BATCH_SIZE = 5000


def create_database(conn) -> None:
    cur = conn.cursor()
    db  = cfg.mysql_database
    cur.execute(
        f"CREATE DATABASE IF NOT EXISTS `{db}` "
        f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cur.execute(f"USE `{db}`")
    conn.commit()
    cur.close()
    print(f"[migrate] Database '{db}' ready.")


def create_tables(conn) -> None:
    cur = conn.cursor()
    cur.execute(f"USE `{cfg.mysql_database}`")
    for table in TABLE_ORDER:
        cur.execute(CREATE_STATEMENTS[table])
        print(f"[migrate] Table '{table}' created (or already exists).")
    conn.commit()
    cur.close()


def migrate_table(table: str, sqlite_conn, mysql_conn) -> int:
    """Copy all rows from one SQLite table into MySQL."""
    # Get column names from SQLite (source of truth)
    col_info = sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()
    columns  = [r[1] for r in col_info]

    cur = sqlite_conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()
    cur.close()

    if not rows:
        print(f"[migrate] {table:<25}  0 rows (empty)")
        return 0

    col_names    = ", ".join([f"`{c}`" for c in columns])
    placeholders = ", ".join(["%s"] * len(columns))
    sql = (
        f"INSERT IGNORE INTO `{table}` ({col_names}) "
        f"VALUES ({placeholders})"
    )

    mysql_cur = mysql_conn.cursor()
    mysql_cur.execute(f"USE `{cfg.mysql_database}`")

    total   = len(rows)
    batches = math.ceil(total / BATCH_SIZE)
    written = 0

    for i in range(batches):
        batch = rows[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
        clean = [tuple(None if v is None else v for v in row) for row in batch]
        mysql_cur.executemany(sql, clean)
        mysql_conn.commit()
        written += len(batch)
        pct = int(written / total * 100)
        print(
            f"\r[migrate] {table:<25} {written:>8,}/{total:,} rows  ({pct}%)",
            end="", flush=True
        )

    print()
    mysql_cur.close()
    return total


def run() -> None:
    print("\n" + "=" * 60)
    print("  TELECOM RA -- SQLite -> MySQL Migration")
    print("=" * 60)

    # 1. Connect to MySQL
    print("\n[migrate] Testing MySQL connection...")
    try:
        mysql_conn = mysql.connector.connect(
            **cfg.mysql_connection_args_no_db()
        )
    except Exception as e:
        print(f"\n[migrate] FAILED to connect: {e}")
        print("[migrate] Check config/config.yaml")
        sys.exit(1)
    print(f"[migrate] Connected to MySQL at {cfg.mysql_host}:{cfg.mysql_port} OK")

    # 2. Check SQLite file
    import os
    if not os.path.exists(str(cfg.sqlite_db_path)):
        print(f"\n[migrate] SQLite not found: {cfg.sqlite_db_path}")
        print("[migrate] Run  python -m src.data.generator  first.")
        sys.exit(1)
    sqlite_conn = sqlite3.connect(str(cfg.sqlite_db_path))
    print(f"[migrate] SQLite file: {cfg.sqlite_db_path} OK")

    # 3. Verify DDL matches SQLite before touching MySQL
    print("\n[migrate] Verifying DDL matches SQLite schema...")
    problems = []
    for table in TABLE_ORDER:
        sqlite_cols = set(
            r[1] for r in sqlite_conn.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
        )
        # Parse DDL column names
        import re
        ddl = CREATE_STATEMENTS[table]
        ddl_cols = set()
        for line in ddl.strip().split("\n"):
            line = line.strip()
            if line and not line.upper().startswith(
                ("CREATE", ")", "INDEX", "PRIMARY", "UNIQUE", "KEY",
                 "ENGINE", "CONSTRAINT")
            ):
                col = line.split()[0].strip("`")
                if col:
                    ddl_cols.add(col)

        missing = sqlite_cols - ddl_cols
        extra   = ddl_cols - sqlite_cols
        if missing or extra:
            problems.append(
                f"  {table}: missing={sorted(missing)} extra={sorted(extra)}"
            )

    if problems:
        print("[migrate] DDL MISMATCH -- cannot migrate:")
        for p in problems:
            print(p)
        sys.exit(1)
    print("[migrate] DDL verified OK\n")

    # 4. Create DB and tables
    create_database(mysql_conn)
    create_tables(mysql_conn)

    # 5. Migrate data
    print("\n[migrate] Copying data (this takes a few minutes)...\n")
    totals = {}
    for table in TABLE_ORDER:
        n = migrate_table(table, sqlite_conn, mysql_conn)
        totals[table] = n

    # 6. Summary
    print()
    print("=" * 60)
    print("  MIGRATION COMPLETE")
    print("=" * 60)
    for table, n in totals.items():
        print(f"  {table:<30} {n:>10,} rows")

    sqlite_conn.close()
    mysql_conn.close()
    print(f"\n[migrate] All data is now in MySQL '{cfg.mysql_database}'")
    print("[migrate] You can now run: python -m src.detection.rule_engine")


if __name__ == "__main__":
    run()