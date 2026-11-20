"""单实例的进程守护：启动、停止、日志环形缓冲、订阅广播。

一个实例一个 InstanceProcess，由 web 层按 id 缓存。日志同时进环形缓冲、磁盘文件、订阅者队列。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import platform
import re
import time
from collections import deque
from pathlib import Path
from typing import Any, Literal

from .model import Instance

State = Literal["stopped", "starting", "running", "stopping", "crashed"]

RING_SIZE = 2000

JOIN_RE = re.compile(r"\]: ([A-Za-z0-9_.-]{1,16}) joined the game")
LEAVE_RE = re.compile(r"\]: ([A-Za-z0-9_.-]{1,16}) left the game")


def decode_line(raw: bytes, preferred: str = "utf-8") -> str:
    """一行输出可能混着编码：Java 日志多为 UTF-8，Windows 原生路径可能是 GBK。

    先按实例配置解，失败再试 UTF-8 与 GB18030，全都失败才替换。
    """
    for encoding in (preferred, "utf-8", "gb18030"):
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode(preferred or "utf-8", errors="replace")


class InstanceProcess:
    def __init__(
        self,
        instance: Instance,
        log_dir: Path,
        ring_size: int = RING_SIZE,
        program: str | None = None,
        args: list[str] | None = None,
    ) -> None:
        self.instance = instance
        self.log_dir = log_dir
        self.ring: deque[str] = deque(maxlen=ring_size)
        self.state: State = "stopped"
        self.exit_code: int | None = None
        self.started_at: float | None = None
        self._program = program or instance.program or instance.java
        self._args = (args if args is not None else (instance.args_override or instance.argv()))
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task[None] | None = None
        self._waiter: asyncio.Task[None] | None = None
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self.players: set[str] = set()
        self.events: deque[dict[str, Any]] = deque(maxlen=200)
        self._event_seq = 0

    # ---------- 状态 ----------

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc and self._proc.returncode is None else None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    def snapshot(self, lines: int = 200) -> list[str]:
        items = list(self.ring)
        return items[-lines:]

    def status(self) -> dict[str, Any]:
        return {
            "id": self.instance.id,
            "name": self.instance.name,
            "state": self.state,
            "pid": self.pid,
            "exit_code": self.exit_code,
            "uptime_s": round(time.time() - self.started_at, 1) if self.started_at else 0,
            "players": sorted(self.players),
        }

    # ---------- 订阅 ----------

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def _broadcast(self, message: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # 慢消费者丢消息，不拖慢服端
                pass

    # ---------- 生命周期 ----------

    async def start(self) -> dict[str, Any]:
        if self.running:
            return {"ok": False, "error": "实例已在运行"}
        missing = self.instance.missing_paths()
        if missing:
            return {"ok": False, "error": "; ".join(missing)}

        self.state = "starting"
        self.exit_code = None
        self.players.clear()
        self._broadcast({"type": "state", "state": self.state})

        creationflags = 0
        preexec = None
        if platform.system().lower().startswith("win"):
            creationflags = getattr(asyncio.subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            preexec = os.setsid

        try:
            self._proc = await asyncio.create_subprocess_exec(
                self._program,
                *self._args,
                cwd=str(self.instance.root),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=creationflags,
                preexec_fn=preexec,
            )
        except (OSError, ValueError) as exc:
            self.state = "crashed"
            self._broadcast({"type": "state", "state": self.state, "error": str(exc)})
            return {"ok": False, "error": f"启动失败: {exc}"}

        self.started_at = time.time()
        self.state = "running"
        self._log_file().parent.mkdir(parents=True, exist_ok=True)
        self._reader = asyncio.create_task(self._read_output())
        self._waiter = asyncio.create_task(self._watch_exit())
        self._push_event("server_start")
        self._broadcast({"type": "state", "state": self.state})
        return {"ok": True, "pid": self._proc.pid}

    async def stop(self, timeout: float = 30.0) -> dict[str, Any]:
        if not self.running:
            return {"ok": False, "error": "实例未在运行"}
        self.state = "stopping"
        self._broadcast({"type": "state", "state": self.state})
        assert self._proc and self._proc.stdin
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self._proc.stdin.write(b"stop\n")
            await self._proc.stdin.drain()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=timeout)
        except TimeoutError:
            return await self.kill()
        return {"ok": True}

    async def kill(self) -> dict[str, Any]:
        if not self.running:
            return {"ok": False, "error": "实例未在运行"}
        assert self._proc
        with contextlib.suppress(ProcessLookupError, OSError):
            if platform.system().lower().startswith("win"):
                self._proc.kill()
            else:
                os.killpg(os.getpgid(self._proc.pid), 9)
        await asyncio.wait_for(self._proc.wait(), timeout=10)
        return {"ok": True}

    async def send(self, text: str) -> dict[str, Any]:
        if not self.running:
            return {"ok": False, "error": "实例未在运行"}
        command = text.replace("\r", "").replace("\n", "").strip()
        if not command:
            return {"ok": False, "error": "命令为空"}
        assert self._proc and self._proc.stdin
        try:
            self._proc.stdin.write(f"{command}\n".encode(self.instance.encoding, "replace"))
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            return {"ok": False, "error": str(exc)}
        self._append(f"> {command}")
        return {"ok": True}

    async def shutdown(self) -> None:
        """面板退出时调用：停子进程与读线程。"""
        if self.running:
            with contextlib.suppress(Exception):
                await self.stop(timeout=10)
        for task in (self._reader, self._waiter):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    # ---------- 输出 ----------

    def _log_file(self) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in self.instance.name)
        return self.log_dir / f"{safe}.log"

    def _track_players(self, line: str) -> None:
        joined = JOIN_RE.search(line)
        if joined:
            self.players.add(joined.group(1))
            self._push_event("player_join", joined.group(1))
            return
        left = LEAVE_RE.search(line)
        if left:
            self.players.discard(left.group(1))
            self._push_event("player_leave", left.group(1))

    def _push_event(self, kind: str, player: str = "") -> None:
        self._event_seq += 1
        self.events.append(
            {"id": self._event_seq, "type": kind, "player": player, "ts": time.time()}
        )

    def recent_events(self, since: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        items = [event for event in self.events if int(event.get("id", 0)) > since]
        return items[-limit:]

    def _append(self, line: str) -> None:
        self.ring.append(line)
        self._track_players(line)
        self._broadcast({"type": "log", "line": line})
        with contextlib.suppress(OSError):
            with self._log_file().open("a", encoding="utf-8", errors="replace") as fh:
                fh.write(line + "\n")

    async def _read_output(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            raw = await self._proc.stdout.readline()
            if not raw:
                break
            line = decode_line(raw, self.instance.encoding).rstrip("\r\n")
            self._append(line)
        # 读完剩余缓冲
        with contextlib.suppress(Exception):
            rest = await self._proc.stdout.read()
            if rest:
                for line in decode_line(rest, self.instance.encoding).splitlines():
                    self._append(line)

    async def _watch_exit(self) -> None:
        assert self._proc
        code = await self._proc.wait()
        self.exit_code = code
        self.players.clear()
        self._push_event("server_crash" if code else "server_stop")
        self.state = "stopped" if code == 0 else "crashed"
        self.started_at = None
        self._broadcast({"type": "exit", "code": code, "state": self.state})
        self._broadcast({"type": "state", "state": self.state})

