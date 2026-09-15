"""
MediKiosk – SQLite Database Connection Helper
Provides thread-safe, context-managed SQLite connections.
Author: MediKiosk Engineering Team | Version: 1.0.0
"""

import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from medikiosk.engine.config import DB_PATH

logger = logging.getLogger(__name__)


def _get_schema_path() -> Path:
    return Path(__file__).parent / "schema.sql"


def init_db(db_path: str = DB_PATH) -> None:
    """Initialise the SQLite database by executing schema.sql."""
    schema_path = _get_schema_path()
    if not schema_path.exists():
        raise FileNotFoundError(f"schema.sql not found at {schema_path}")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_connection(db_path) as conn:
        statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
        for stmt in statements:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as exc:
                logger.debug("DDL skipped: %s | %s", stmt[:60], exc)
        conn.commit()
    logger.info("Database initialised at %s", db_path)


@contextmanager
def get_connection(db_path: str = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager yielding a sqlite3.Connection with:
      - WAL journal mode
      - Row factory (dict-like column access)
      - Foreign key enforcement
      - 30-second busy timeout
    """
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_one(query: str, params: tuple = (), db_path: str = DB_PATH):
    with get_connection(db_path) as conn:
        return conn.execute(query, params).fetchone()


def fetch_all(query: str, params: tuple = (), db_path: str = DB_PATH):
    with get_connection(db_path) as conn:
        return conn.execute(query, params).fetchall()


def execute_write(query: str, params: tuple = (), db_path: str = DB_PATH) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor.rowcount


def execute_many(query: str, params_list: list, db_path: str = DB_PATH) -> int:
    if not params_list:
        return 0
    with get_connection(db_path) as conn:
        cursor = conn.executemany(query, params_list)
        conn.commit()
        return cursor.rowcount


def row_to_dict(row) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list) -> list:
    return [dict(r) for r in rows]
