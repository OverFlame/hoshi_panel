"""路径安全：所有文件操作都必须落在实例目录内。"""

from __future__ import annotations

from pathlib import Path


class UnsafePath(ValueError):
    """路径越界或非法。"""


def resolve_within(root: Path, relative: str) -> Path:
    """把相对路径解析到 root 下，越界就抛错。"""
    base = root.resolve()
    text = str(relative or "").replace("\\", "/").strip()

    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        raise UnsafePath("不接受绝对路径")
    if any(part == ".." for part in text.split("/")):
        raise UnsafePath("不接受 .. 路径")

    target = (base / text).resolve()
    if target != base and base not in target.parents:
        raise UnsafePath(f"越界: {relative}")
    return target


def is_inside(root: Path, candidate: Path) -> bool:
    base = root.resolve()
    try:
        resolved = candidate.resolve()
    except OSError:
        return False
    return resolved == base or base in resolved.parents
