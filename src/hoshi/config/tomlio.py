"""极简 TOML 序列化。

只处理本项目用得到的类型：布尔、整数、字符串、字符串列表，以及一层嵌套表。
读用标准库 `tomllib`，写自己做，避免多一个依赖。
"""

from __future__ import annotations

from typing import Any


def _fmt_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        escaped = escaped.replace("\n", "\\n").replace("\t", "\\t")
        return f'"{escaped}"'
    raise TypeError(f"不支持的类型: {type(value)!r}")


def dumps(data: dict[str, Any]) -> str:
    """把「组名 → 值或子表」的字典写成 TOML。"""
    scalars: list[str] = []
    tables: list[str] = []

    for key, value in data.items():
        if isinstance(value, dict):
            continue
        scalars.append(f"{key} = {_fmt_scalar(value)}")

    for group, values in data.items():
        if not isinstance(values, dict):
            continue
        lines = [f"[{group}]"]
        for key, value in values.items():
            if isinstance(value, dict):
                raise TypeError(f"只支持一层嵌套: {group}.{key}")
            if isinstance(value, list):
                inner = ", ".join(_fmt_scalar(v) for v in value)
                lines.append(f"{key} = [{inner}]")
            else:
                lines.append(f"{key} = {_fmt_scalar(value)}")
        tables.append("\n".join(lines))

    parts = []
    if scalars:
        parts.append("\n".join(scalars))
    parts.extend(tables)
    return "\n\n".join(parts) + "\n"


def loads(text: str) -> dict[str, Any]:
    import tomllib

    return tomllib.loads(text)
