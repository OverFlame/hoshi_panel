"""玩家位置轮询：RCON 拉坐标，缓存给地图用。

RCON 不可用时返回空集合，让界面显示「未连接」，不阻塞其它功能。
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from dataclasses import dataclass, field

from .rcon import RconError, command

POS_RE = re.compile(r"\[(-?\d+(?:\.\d+)?)[dfls]?,\s*(-?\d+(?:\.\d+)?)[dfls]?,\s*(-?\d+(?:\.\d+)?)[dfls]?\]")
DIM_RE = re.compile(r'entity data:\s*"([^"]+)"|Dimension:\s*([a-z0-9_:.-]+)', re.IGNORECASE)


@dataclass
class PlayerPos:
    name: str
    x: float
    y: float
    z: float
    dimension: str = "minecraft:overworld"
    updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "z": round(self.z, 2),
            "dimension": self.dimension,
            "age_s": round(time.time() - self.updated, 1),
        }


class PlayerPoller:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 25575,
        password: str = "",
        interval: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.interval = max(1.0, interval)
        self.positions: dict[str, PlayerPos] = {}
        self.last_error = ""
        self.last_ok = 0.0
        self._task: asyncio.Task[None] | None = None

    async def poll_once(self) -> list[str]:
        try:
            listing = await command(self.host, self.port, self.password, "list")
            if not listing.ok:
                self.last_error = listing.body
                return []
            names = _parse_list(listing.body)
            for name in names:
                pos = await command(
                    self.host, self.port, self.password, f"data get entity {name} Pos"
                )
                if not pos.ok:
                    continue
                match = POS_RE.search(pos.body)
                if not match:
                    continue
                dimension = "minecraft:overworld"
                dim = await command(
                    self.host, self.port, self.password, f"data get entity {name} Dimension"
                )
                if dim.ok:
                    found = DIM_RE.search(dim.body)
                    if found:
                        dimension = found.group(1) or found.group(2)
                self.positions[name] = PlayerPos(
                    name=name,
                    x=float(match.group(1)),
                    y=float(match.group(2)),
                    z=float(match.group(3)),
                    dimension=dimension,
                )
            stale = [name for name in self.positions if name not in names]
            for name in stale:
                self.positions.pop(name, None)
            self.last_ok = time.time()
            self.last_error = ""
            return names
        except RconError as exc:
            self.last_error = str(exc)
            return []

    async def start(self) -> None:
        if self._task is not None:
            return

        async def loop() -> None:
            while True:
                await self.poll_once()
                await asyncio.sleep(self.interval)

        self._task = asyncio.create_task(loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def snapshot(self) -> dict[str, object]:
        return {
            "connected": bool(self.last_ok) and not self.last_error,
            "error": self.last_error,
            "players": [item.to_dict() for item in self.positions.values()],
        }


def _parse_list(body: str) -> list[str]:
    """解析 `There are 2 of a max of 20 players online: Steve, Alex`。"""
    if ":" not in body:
        return []
    names = body.split(":", 1)[1].strip()
    if not names:
        return []
    return [item.strip() for item in names.split(",") if item.strip()]
