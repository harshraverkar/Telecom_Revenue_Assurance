"""
src/utils/db.py
---------------
MySQL connection and query utilities.

Usage in any module:
    from src.utils.db import run_query, run_update, run_many

    df = run_query("SELECT * FROM cdr WHERE leakage_flag = 1 LIMIT 5")
    run_update("UPDATE cdr SET sql_detected_leakage_type = %s WHERE cdr_id = %s",
               ("L1_unbilled", "CDR00001234"))
"""

import mysql.connector
import pandas as pd
from src.utils.config import cfg


def get_connection(with_database: bool = True):
    """Open and return a MySQL connection."""
    args = cfg.mysql_connection_args() if with_database \
           else cfg.mysql_connection_args_no_db()
    return mysql.connector.connect(**args)


def run_query(sql: str, params: tuple = None) -> pd.DataFrame:
    """
    Run a SELECT and return results as a DataFrame.
    Uses cursor-based fetch so no SQLAlchemy needed.
    """
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)   # returns rows as dicts
    try:
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        return pd.DataFrame(rows)
    finally:
        cur.close()
        conn.close()


def run_update(sql: str, params: tuple = None) -> int:
    """Run INSERT / UPDATE / DELETE. Returns rows affected."""
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute(sql, params or ())
        conn.commit()
        return cur.rowcount
    finally:
        cur.close()
        conn.close()


def run_many(sql: str, rows: list) -> int:
    """Batch INSERT / UPDATE -- faster than calling run_update in a loop."""
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.executemany(sql, rows)
        conn.commit()
        return cur.rowcount
    finally:
        cur.close()
        conn.close()


def test_connection() -> bool:
    """Test MySQL connection. Returns True if OK."""
    try:
        conn = get_connection(with_database=False)
        conn.close()
        print(f"[db] Connected to MySQL at "
              f"{cfg.mysql_host}:{cfg.mysql_port} as '{cfg.mysql_user}' OK")
        return True
    except Exception as e:
        print(f"[db] Connection FAILED: {e}")
        print("[db] Fix config/config.yaml -> mysql section")
        return False
