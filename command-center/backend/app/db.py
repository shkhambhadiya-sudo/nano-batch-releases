"""SQLite access. One connection per call site, WAL mode, rows as dicts."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
_initialised: set[str] = set()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def init_db(path: Path | None = None) -> None:
    path = path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.commit()
    finally:
        conn.close()
    _initialised.add(str(path))


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = path or settings.db_path
    if str(path) not in _initialised:
        init_db(path)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def q(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
    return conn.execute(sql, params).fetchall()


def one(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
    rows = conn.execute(sql, params).fetchall()
    return rows[0] if rows else None


def insert(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    cols = ", ".join(row)
    marks = ", ".join(f":{k}" for k in row)
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", _enc(row))


def update(conn: sqlite3.Connection, table: str, id_: str, fields: dict[str, Any]) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    conn.execute(f"UPDATE {table} SET {sets} WHERE id = :_id", {**_enc(fields), "_id": id_})


def _enc(row: dict[str, Any]) -> dict[str, Any]:
    # JSON-encode lists/dicts so callers can pass Python structures for JSON columns.
    return {k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in row.items()}


def loads(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default
