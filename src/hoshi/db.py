"""SQLite 初始化。

只存面板自己的状态：元信息、审计骨架。实例配置仍在文件里，便于手工排查与迁移。
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 1

DDL = (
    """
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT,
        result TEXT NOT NULL,
        detail TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit (ts)
    """,
)


def now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init(path: Path) -> sqlite3.Connection:
    conn = connect(path)
    for statement in DDL:
        conn.execute(statement)
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('created_at', ?)",
            (now(),),
        )
    conn.commit()
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def record(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    target: str = "",
    result: str = "ok",
    detail: str = "",
) -> None:
    conn.execute(
        "INSERT INTO audit (ts, actor, action, target, result, detail) VALUES (?, ?, ?, ?, ?, ?)",
        (now(), actor, action, target, result, detail),
    )
    conn.commit()
