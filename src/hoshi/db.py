"""SQLite 初始化。

只存面板自己的状态：元信息、审计骨架。实例配置仍在文件里，便于手工排查与迁移。
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
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
    """
    CREATE TABLE IF NOT EXISTS bot_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_hash TEXT NOT NULL UNIQUE,
        group_id TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        created TEXT NOT NULL,
        revoked INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        actor TEXT NOT NULL,
        key TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT
    )
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


def create_bot_token(conn: sqlite3.Connection, group_id: str, label: str = "") -> tuple[int, str]:
    """返回 (id, 明文令牌)。只存散列。"""
    import hashlib
    import secrets

    token = "hoshi_" + secrets.token_urlsafe(24)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    cursor = conn.execute(
        "INSERT INTO bot_tokens (token_hash, group_id, label, created) VALUES (?, ?, ?, ?)",
        (digest, group_id, label, now()),
    )
    conn.commit()
    return int(cursor.lastrowid or 0), token


def find_bot_token(conn: sqlite3.Connection, token: str) -> dict[str, object] | None:
    import hashlib

    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = conn.execute(
        "SELECT id, group_id, label, created FROM bot_tokens WHERE token_hash = ? AND revoked = 0",
        (digest,),
    ).fetchone()
    return dict(row) if row else None


def list_bot_tokens(conn: sqlite3.Connection) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT id, group_id, label, created FROM bot_tokens WHERE revoked = 0 ORDER BY id DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def revoke_bot_token(conn: sqlite3.Connection, token_id: int) -> bool:
    cursor = conn.execute("UPDATE bot_tokens SET revoked = 1 WHERE id = ? AND revoked = 0", (token_id,))
    conn.commit()
    return bool(cursor.rowcount)


def log_setting(
    conn: sqlite3.Connection,
    actor: str,
    key: str,
    old_value: object,
    new_value: object,
) -> None:
    conn.execute(
        "INSERT INTO settings_log (ts, actor, key, old_value, new_value) VALUES (?, ?, ?, ?, ?)",
        (now(), actor, key, _short(old_value), _short(new_value)),
    )
    conn.commit()


def recent_settings(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT ts, actor, key, old_value, new_value FROM settings_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def recent_audit(
    conn: sqlite3.Connection, limit: int = 100, action: str = ""
) -> list[dict[str, object]]:
    if action:
        rows = conn.execute(
            "SELECT ts, actor, action, target, result, detail FROM audit "
            "WHERE action LIKE ? ORDER BY id DESC LIMIT ?",
            (f"{action}%", limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT ts, actor, action, target, result, detail FROM audit ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def cleanup(conn: sqlite3.Connection, keep_days: int = 90) -> int:
    """删除过旧审计，返回删除行数。"""
    cutoff = (datetime.now(UTC).astimezone() - timedelta(days=keep_days)).isoformat(
        timespec="seconds"
    )
    cursor = conn.execute("DELETE FROM audit WHERE ts < ?", (cutoff,))
    conn.commit()
    return cursor.rowcount or 0


def _short(value: object) -> str:
    text = "" if value is None else str(value)
    if len(text) > 80:
        return text[:77] + "..."
    return text


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
