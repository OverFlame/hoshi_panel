"""bot 只读接口的限速。

按令牌（群）每分钟 10 次，按群成员每分钟 1 次。不依赖会话。
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class TokenLimiter:
    def __init__(self, group_limit: int = 10, user_limit: int = 1, window: int = 60) -> None:
        self.group_limit = max(1, group_limit)
        self.user_limit = max(1, user_limit)
        self.window = window
        self._group: dict[int, deque[float]] = defaultdict(deque)
        self._user: dict[tuple[int, str], deque[float]] = defaultdict(deque)

    def _hit(self, bucket: deque[float], limit: int, now: float) -> int:
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= limit:
            return int(self.window - (now - bucket[0])) + 1
        bucket.append(now)
        return 0

    def check(self, token_id: int, user: str) -> int:
        """返回 0 表示放行，否则是建议的等待秒数。"""
        now = time.time()
        wait = self._hit(self._group[token_id], self.group_limit, now)
        if wait:
            return wait
        if user:
            wait = self._hit(self._user[(token_id, user)], self.user_limit, now)
        return wait
