"""配置加载与保存。

优先级：命令行 > 配置文件 > schema 默认值。每个值都记录来源，设置页要显示它。
配置文件里不认识的键会被原样保留，保存时写回去，避免手写的配置被吞掉。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from . import tomlio
from .schema import BY_KEY, SCHEMA

Source = Literal["default", "file", "cli"]


class ConfigError(Exception):
    """配置有问题，附带全部错误信息。"""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass
class Entry:
    value: Any
    source: Source


@dataclass
class Config:
    entries: dict[str, Entry] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    def get(self, key: str) -> Any:
        return self.entries[key].value

    def source(self, key: str) -> Source:
        return self.entries[key].source

    def as_public(self) -> list[dict[str, Any]]:
        """给 /api/settings 用的结构，敏感项打码。"""
        out = []
        for item in SCHEMA:
            entry = self.entries[item.key]
            value = entry.value
            if item.secret and value:
                value = "***"
            out.append(
                {
                    "key": item.key,
                    "group": item.group,
                    "label": item.label,
                    "summary": item.summary,
                    "why": item.why,
                    "risk": item.risk,
                    "restart": item.restart,
                    "kind": item.kind,
                    "value": value,
                    "source": entry.source,
                }
            )
        return out

    def validate(self) -> list[str]:
        errors: list[str] = []
        for item in SCHEMA:
            value = self.entries[item.key].value
            try:
                item.validate(value)
            except ValueError as exc:
                errors.append(str(exc))
        errors.extend(check_required(self))
        return errors

    def to_toml(self) -> str:
        data: dict[str, Any] = {}
        for item in SCHEMA:
            group, _, leaf = item.key.partition(".")
            data.setdefault(group, {})[leaf] = self.entries[item.key].value
        for group, values in self.extra.items():
            if group in data and isinstance(values, dict):
                data[group].update(values)
            else:
                data[group] = values
        return tomlio.dumps(data)


def check_required(config: Config) -> list[str]:
    """处理 schema 里的 requires 声明。"""
    errors: list[str] = []
    for item in SCHEMA:
        if not item.requires:
            continue
        current = config.get(item.key)
        if current == item.default:
            continue
        for dep_key, rule in item.requires:
            if dep_key not in BY_KEY:
                continue
            value = config.get(dep_key)
            if rule == "not_empty" and not value:
                errors.append(f"{item.key}: 需要先设置 {dep_key}")
            elif rule == "true" and not value:
                errors.append(f"{item.key}: 需要先开启 {dep_key}")
    return errors


def flatten(data: dict[str, Any]) -> dict[str, Any]:
    """把嵌套表压成点号键。"""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            for inner_key, inner_value in flatten(value).items():
                out[f"{key}.{inner_key}"] = inner_value
        else:
            out[key] = value
    return out


def load(path: Path | None = None, cli: dict[str, str] | None = None) -> Config:
    """按优先级解决问题，返回带来源标记的配置。"""
    config = Config(path=path)
    for item in SCHEMA:
        config.entries[item.key] = Entry(item.default, "default")

    if path is not None and path.exists():
        raw = tomlio.loads(path.read_text(encoding="utf-8"))
        flat = flatten(raw)
        for key, value in flat.items():
            item = BY_KEY.get(key)
            if item is None:
                group, _, leaf = key.partition(".")
                if leaf:
                    config.extra.setdefault(group, {})[leaf] = value
                else:
                    config.extra[group] = value
                continue
            try:
                config.entries[key] = Entry(item.coerce(value), "file")
            except ValueError as exc:
                raise ConfigError([str(exc)]) from exc

    for key, raw_value in (cli or {}).items():
        item = BY_KEY.get(key)
        if item is None:
            raise ConfigError([f"未知的配置项: {key}"])
        try:
            value = item.coerce(raw_value)
        except ValueError as exc:
            raise ConfigError([str(exc)]) from exc
        config.entries[key] = Entry(value, "cli")

    return config


def save(config: Config, path: Path | None = None) -> Path:
    target = path or config.path
    if target is None:
        raise ConfigError(["没有配置文件路径"])
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(config.to_toml(), encoding="utf-8")
    tmp.replace(target)
    return target


def default_path() -> Path:
    return Path.cwd() / "hoshi.toml"


__all__ = ["Config", "ConfigError", "Entry", "default_path", "flatten", "load", "save"]
