"""
src/utils/config.py
-------------------
Reads config/config.yaml and exposes settings to all modules.

Usage:
    from src.utils.config import cfg

    cfg.mysql_host       # "localhost"
    cfg.mysql_database   # "telecom_ra"
    cfg.sqlite_db_path   # absolute path to telecom_ra.db  (Path object)
    cfg.db_path          # same -- alias used by generator.py
    cfg.n_subscribers    # 3000
"""

import os
import yaml
from pathlib import Path


def _find_root() -> Path:
    p = Path(__file__).resolve()
    for _ in range(6):
        p = p.parent
        if (p / "config" / "config.yaml").exists():
            return p
    return Path.cwd()


PROJECT_ROOT = _find_root()


class Config:
    def __init__(self):
        cfg_file = PROJECT_ROOT / "config" / "config.yaml"
        if not cfg_file.exists():
            raise FileNotFoundError(
                f"config.yaml not found at {cfg_file}\n"
                f"Make sure you are running from the project root."
            )
        with open(cfg_file, encoding='utf-8') as f:
            raw = yaml.safe_load(f)

        # -- MySQL ---------------------------------------------
        m = raw.get("mysql", {})
        self.mysql_host     = m.get("host",     "localhost")
        self.mysql_port     = int(m.get("port", 3306))
        self.mysql_user     = m.get("user",     "root")
        self.mysql_password = m.get("password", "")
        self.mysql_database = m.get("database", "telecom_ra")
        self.mysql_charset  = m.get("charset",  "utf8mb4")

        # -- SQLite (source for migration) ---------------------
        s = raw.get("sqlite", {})
        sqlite_rel          = s.get("db_path", "data/raw/telecom_ra.db")
        self.sqlite_db_path = PROJECT_ROOT / sqlite_rel  # Path object
        self.db_path        = self.sqlite_db_path         # alias for generator.py

        # -- Data generation -----------------------------------
        d = raw.get("data", {})
        self.n_subscribers = int(d.get("n_subscribers", 3000))
        self.n_towers      = int(d.get("n_towers",      200))
        self.n_days        = int(d.get("n_days",        90))
        self.leakage_rate  = float(d.get("leakage_rate", 0.07))
        self.random_seed   = int(d.get("random_seed",   42))

        # -- Project root --------------------------------------
        self.project_root = PROJECT_ROOT

    def mysql_connection_args(self) -> dict:
        """Ready to pass to mysql.connector.connect()"""
        return {
            "host":     self.mysql_host,
            "port":     self.mysql_port,
            "user":     self.mysql_user,
            "password": self.mysql_password,
            "database": self.mysql_database,
            "charset":  self.mysql_charset,
        }

    def mysql_connection_args_no_db(self) -> dict:
        """Without database -- used when creating the DB."""
        args = self.mysql_connection_args()
        args.pop("database")
        return args

    def ensure_dirs(self):
        """Create data/raw if it doesn't exist."""
        self.sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)


# Module-level singleton
cfg = Config()

# Standalone function alias (generator calls ensure_dirs() as a function)
def ensure_dirs():
    cfg.ensure_dirs()
