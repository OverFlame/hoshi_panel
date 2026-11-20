"""登录限速与锁定。

按来源 IP 与账号名各自计数。超限锁定一段时间，成功登录清零。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Attempt:
    failures: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class LoginThrottle:
    def __init__(self, limit: int = 5, window_seconds: int = 300, lock_seconds: int = 900) -> None:
        self.limit = max(1, limit)
        self.window = window_seconds
        self.lock = lock_seconds
        self._attempts: dict[str, Attempt] = {}

    def _prune(self, attempt: Attempt, now: float) -> None:
        attempt.failures = [t for t in attempt.failures if now - t < self.window]

    def check(self, *keys: str) -> int:
        """返回剩余锁定秒数，0 表示可以尝试。"""
        now = time.time()
        remaining = 0.0
        for key in keys:
            attempt = self._attempts.get(key)
            if not attempt:
                continue
            if attempt.locked_until > now:
                remaining = max(remaining, attempt.locked_until - now)
        return int(remaining) + 1 if remaining > 0 else 0

    def fail(self, *keys: str) -> int:
        """记一次失败，返回锁定秒数（0 表示还没锁）。"""
        now = time.time()
        locked = 0
        for key in keys:
            attempt = self._attempts.setdefault(key, Attempt())
            self._prune(attempt, now)
            attempt.failures.append(now)
            if len(attempt.failures) >= self.limit:
                attempt.locked_until = now + self.lock
                attempt.failures.clear()
                locked = self.lock
        return locked

    def reset(self, *keys: str) -> None:
        for key in keys:
            self._attempts.pop(key, None)

    def cleanup(self, max_age: float = 86400) -> None:
        now = time.time()
        stale = [
            key
            for key, attempt in self._attempts.items()
            if attempt.locked_until < now
            and (not attempt.failures or now - max(attempt.failures) > max_age)
        ]
        for key in stale:
            self._attempts.pop(key, None)
