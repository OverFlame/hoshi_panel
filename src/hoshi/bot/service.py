"""bot 查询的数据组装：状态、玩家、最近事件。"""

from __future__ import annotations

import time
from typing import Any

from ..config import Config
from ..instances import InstanceProcess


def status_payload(proc: InstanceProcess, instance_name: str) -> dict[str, Any]:
    snapshot = proc.snapshot(200)
    last = ""
    for line in reversed(snapshot):
        text = line.strip()
        if text and not text.startswith(">"):
            last = text[:160]
            break
    data: dict[str, Any] = {
        "instance": instance_name,
        "state": proc.state,
        "pid": proc.pid,
        "uptime_s": round(time.time() - proc.started_at) if proc.started_at else 0,
        "players": {
            "online": len(proc.players),
            "names": sorted(proc.players),
        },
        "memory": {},
        "tps": None,
        "last_event": {"text": last},
    }
    return data


def render_text(data: dict[str, Any], config: Config) -> str:
    template = str(
        config.get("bot.status_template")
        or "实例 {instance} 状态 {state}\n在线 {online} 人{names}\n{last_event}"
    )
    names = data.get("players", {}).get("names", [])
    values = {
        "instance": data.get("instance", ""),
        "state": data.get("state", ""),
        "online": data.get("players", {}).get("online", 0),
        "max": data.get("players", {}).get("max", "?"),
        "names": ("：" + "、".join(names)) if names else "",
        "tps": data.get("tps") if data.get("tps") is not None else "?",
        "uptime": _uptime(data.get("uptime_s")),
        "last_event": (data.get("last_event") or {}).get("text", "无"),
    }
    text = template
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return "\n".join(line for line in text.splitlines() if line.strip())


def _uptime(seconds: int | None) -> str:
    if not seconds:
        return "未运行"
    hours, rest = divmod(int(seconds), 3600)
    minutes = rest // 60
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m"
