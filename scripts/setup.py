"""
scripts/setup.py
----------------
Run this ONCE when a team member sets up the project.

What it does:
    Step 1 -- Test MySQL connection
    Step 2 -- Migrate SQLite -> MySQL (copies all data)
    Step 3 -- Verify row counts in MySQL match SQLite

Usage:
    python scripts/setup.py

Before running:
    1. Edit config/config.yaml with your MySQL host/user/password
    2. Make sure data/raw/telecom_ra.db exists
       (run python -m src.data.generator if it doesn't)
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mysql.connector
import sqlite3
from src.utils.config import cfg


def step1_test_connection():
    print("\n" + "="*55)
    print("  STEP 1 -- Test MySQL connection")
    print("="*55)
    print(f"  Host     : {cfg.mysql_host}:{cfg.mysql_port}")
    print(f"  User     : {cfg.mysql_user}")
    print(f"  Database : {cfg.mysql_database}")
    print()

    try:
        conn = mysql.connector.connect(**cfg.mysql_connection_args_no_db())
        ver  = conn.get_server_info()
        conn.close()
        print(f"  MySQL version {ver} -- Connection OK OK")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        print()
        print("  Fix:")
        print("  1. Open config/config.yaml")
        print("  2. Set correct host, user, password, port")
        print("  3. Run this script again")
        return False


def step2_migrate():
    print("\n" + "="*55)
    print("  STEP 2 -- Migrate data to MySQL")
    print("="*55)

    if not os.path.exists(cfg.sqlite_db_path):
        print(f"  SQLite DB not found: {cfg.sqlite_db_path}")
        print("  Run: python -m src.data.generator")
        return False

    size_mb = os.path.getsize(cfg.sqlite_db_path) // 1024 // 1024
    print(f"  SQLite source: {cfg.sqlite_db_path} ({size_mb} MB)")
    print()

    from src.data.migrate import run
    run()
    return True


def step3_verify():
    print("\n" + "="*55)
    print("  STEP 3 -- Verify row counts")
    print("="*55)

    sqlite_conn = sqlite3.connect(cfg.sqlite_db_path)
    mysql_conn  = mysql.connector.connect(**cfg.mysql_connection_args())
    mysql_cur   = mysql_conn.cursor()

    tables = ["plans", "cell_towers", "subscribers", "cdr",
              "mediation_events", "rating_events",
              "billing_records", "roaming_settlements", "leakage_audit"]

    all_ok = True
    print(f"  {'Table':<25} {'SQLite':>10} {'MySQL':>10}  Match?")
    print("  " + "-"*50)
    for t in tables:
        sq = sqlite_conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        mysql_cur.execute(f"SELECT COUNT(*) FROM `{t}`")
        my = mysql_cur.fetchone()[0]
        ok = "OK" if sq == my else "X MISMATCH"
        if sq != my: all_ok = False
        print(f"  {t:<25} {sq:>10,} {my:>10,}  {ok}")

    sqlite_conn.close()
    mysql_cur.close()
    mysql_conn.close()

    print()
    if all_ok:
        print("  All tables match OK")
        print()
        print("  Setup complete! Next steps:")
        print("  -> python -m src.detection.rule_engine")
        print("  -> Open MySQL Workbench and query the telecom_ra database")
    else:
        print("  Some tables have mismatches -- re-run migration:")
        print("  -> python scripts/setup.py")

    return all_ok


if __name__ == "__main__":
    if not step1_test_connection():
        sys.exit(1)
    if not step2_migrate():
        sys.exit(1)
    step3_verify()
