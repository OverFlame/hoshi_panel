"""内存会话表。

单人使用，进程重启即失效；R2 会加持久化与 TOTP。Cookie 只存随机 token，明文不落库。
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

COOKIE_NAME = "hoshi_session"


@dataclass
class Session:
    token: str
    username: str
    created: float
    last_seen: float
    idle_seconds: int
    absolute_seconds: int
    meta: dict[str, str] = field(default_factory=dict)

    def expired(self, now: float | None = None) -> bool:
        current = now if now is not None else time.time()
        return (current - self.last_seen) > self.idle_seconds or (
            current - self.created
        ) > self.absolute_seconds


class SessionStore:
    def __init__(self, idle_minutes: int = 30, absolute_hours: int = 12) -> None:
        self.idle_seconds = max(60, idle_minutes * 60)
        self.absolute_seconds = max(600, absolute_hours * 3600)
        self._sessions: dict[str, Session] = {}

    def create(self, username: str, meta: dict[str, str] | None = None) -> Session:
        now = time.time()
        session = Session(
            token=secrets.token_urlsafe(32),
            username=username,
            created=now,
            last_seen=now,
            idle_seconds=self.idle_seconds,
            absolute_seconds=self.absolute_seconds,
            meta=meta or {},
        )
        self._sessions[session.token] = session
        return session

    def get(self, token: str | None) -> Session | None:
        if not token:
            return None
        session = self._sessions.get(token)
        if session is None:
            return None
        if session.expired():
            self._sessions.pop(token, None)
            return None
        session.last_seen = time.time()
        return session

    def revoke(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def revoke_others(self, keep_token: str | None) -> int:
        """改密码后踢掉其它会话，保留当前这一个。"""
        if not keep_token:
            return 0
        dropped = [token for token in self._sessions if token != keep_token]
        for token in dropped:
            self._sessions.pop(token, None)
        return len(dropped)

    def revoke_all(self) -> None:
        self._sessions.clear()

    def __len__(self) -> int:  # 便于测试
        return len(self._sessions)
