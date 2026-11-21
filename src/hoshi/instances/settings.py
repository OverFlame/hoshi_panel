"""实例级设置：谁能按实例覆盖，怎么解析出最终生效值。

优先级：实例覆盖 → 全局配置 → schema 默认值。
"""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..config.schema import BY_KEY
from .model import Instance

PER_INSTANCE_KEYS: tuple[str, ...] = (
    "map.enabled",
    "map.render_threads",
    "map.hires_distance",
    "map.accept_download",
    "map.player_poll_seconds",
    "map.hires_enabled",
    "map.flat_view",
    "map.free_flight_view",
    "map.perspective_view",
    "map.render_radius",
    "map.remove_caves_below_y",
    "map.min_inhabited_time",
    "map.compression",
    "map.update_cooldown",
    "map.web_port",
    "mods.side_lookup",
    "console.command_mode",
    "console.extra_commands",
)


def is_per_instance(key: str) -> bool:
    return key in PER_INSTANCE_KEYS


def resolve(config: Config, instance: Instance | None, key: str) -> tuple[Any, str]:
    """返回 (生效值, 来源)。来源取值 instance、global、default。"""
    if instance is not None and key in instance.settings:
        return instance.settings[key], "instance"
    if key in BY_KEY:
        entry = config.entries.get(key)
        if entry is not None:
            return entry.value, "default" if entry.source == "default" else "global"
    return None, "default"


def effective(config: Config, instance: Instance | None) -> dict[str, dict[str, Any]]:
    """把可覆盖项一次性算出来，给设置页用。"""
    out: dict[str, dict[str, Any]] = {}
    for key in PER_INSTANCE_KEYS:
        value, source = resolve(config, instance, key)
        item = BY_KEY.get(key)
        out[key] = {
            "key": key,
            "value": value,
            "source": source,
            "label": item.label if item else key,
            "summary": item.summary if item else "",
            "kind": item.kind if item else "str",
        }
    return out


def coerce_value(key: str, raw: Any) -> Any:
    item = BY_KEY.get(key)
    if item is None:
        raise ValueError(f"未知设置项: {key}")
    value = item.coerce(raw)
    item.validate(value)
    return value
