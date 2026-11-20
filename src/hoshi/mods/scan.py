"""读取模组 jar 的元数据，推断侧别。

三处来源：fabric.mod.json 的 environment、mods.toml 的 side、内置的常见客户端模组名单。
判不出就标记 unknown，不猜。
"""

from __future__ import annotations

import hashlib
import json
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

CLIENT_ONLY_HINTS = {
    "embeddium",
    "sodium",
    "iris",
    "oculus",
    "rubidium",
    "entityculling",
    "dynamiclights",
    "xaeros_minimap",
    "xaerosminimap",
    "journeymap",
    "shoulder-surfing-reloaded",
    "controlling",
    "betterf3",
    "zoomify",
    "justzoom",
    "toastcontrol",
    "gamma-utils",
    "drippyloadingscreen",
    "fancymenu",
    "malilib",
    "itemscroller",
    "litematica",
    "minihud",
    "tweakeroo",
    "reauth",
    "modernfix-client",
}


@dataclass
class ModInfo:
    file: str
    enabled: bool
    size: int
    sha1: str = ""
    mod_id: str = ""
    name: str = ""
    version: str = ""
    side: str = "unknown"
    side_source: str = ""
    advice: str = ""
    loaders: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "enabled": self.enabled,
            "size": self.size,
            "sha1": self.sha1,
            "mod_id": self.mod_id,
            "name": self.name,
            "version": self.version,
            "side": self.side,
            "side_source": self.side_source,
            "advice": self.advice,
            "loaders": self.loaders,
        }


def sha1_of(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _advice_for(side: str, enabled: bool) -> str:
    if side == "client":
        return "客户端模组，服务端可不装" if enabled else "已停用"
    if side == "both":
        return "两侧都需要" if enabled else "已停用，客户端可能进不来"
    if side == "server":
        return "服务端模组" if enabled else "已停用"
    return "侧别未知，保留为妙" if enabled else "已停用"


def _read_fabric(z: zipfile.ZipFile) -> tuple[str, str, str, str]:
    try:
        data = json.loads(z.read("fabric.mod.json").decode("utf-8", "replace"))
    except (KeyError, json.JSONDecodeError):
        return "", "", "", ""
    env = str(data.get("environment", "")).lower()
    side = {"client": "client", "server": "server", "*": "both"}.get(env, "")
    return (
        str(data.get("id", "")),
        str(data.get("name", "")),
        str(data.get("version", "")),
        side,
    )


def _read_forge(z: zipfile.ZipFile) -> tuple[str, str, str, str]:
    try:
        raw = z.read("META-INF/mods.toml")
    except KeyError:
        try:
            raw = z.read("META-INF/neoforge.mods.toml")
        except KeyError:
            return "", "", "", ""
    try:
        data = tomllib.loads(raw.decode("utf-8", "replace"))
    except tomllib.TOMLDecodeError:
        return "", "", "", ""
    mods = data.get("mods") or []
    if not isinstance(mods, list) or not mods:
        return "", "", "", ""
    first = mods[0] if isinstance(mods[0], dict) else {}
    side_map = {"CLIENT": "client", "SERVER": "server", "BOTH": "both"}
    side = side_map.get(str(first.get("side", "")).upper(), "")
    return (
        str(first.get("modId", "")),
        str(first.get("displayName", "")),
        str(first.get("version", "")),
        side,
    )


def read_jar(path: Path) -> ModInfo:
    info = ModInfo(file=path.name, enabled=not path.name.endswith(".disabled"), size=path.stat().st_size)
    if path.suffix == ".disabled":
        info.enabled = False
    try:
        with zipfile.ZipFile(path) as archive:
            mod_id, name, version, side = _read_fabric(archive)
            source = "fabric.mod.json" if side else ""
            if not side:
                mod_id2, name2, version2, side2 = _read_forge(archive)
                mod_id = mod_id or mod_id2
                name = name or name2
                version = version or version2
                side, source = (side2, "mods.toml") if side2 else (side, source)
    except (zipfile.BadZipFile, OSError):
        return info

    info.mod_id, info.name, info.version = mod_id, name or mod_id, version
    if not side:
        stem = path.name.lower().replace(".jar.disabled", "").replace(".jar", "")
        if any(hint in stem for hint in CLIENT_ONLY_HINTS):
            side, source = "client", "内置名单"
    info.side = side or "unknown"
    info.side_source = source or ("内置名单" if side else "")
    info.advice = _advice_for(info.side, info.enabled)
    return info


def scan_mods(mods_dir: Path, with_sha1: bool = True) -> list[ModInfo]:
    if not mods_dir.is_dir():
        return []
    items: list[ModInfo] = []
    for path in sorted(mods_dir.iterdir()):
        name = path.name.lower()
        if not (name.endswith(".jar") or name.endswith(".jar.disabled")):
            continue
        if not path.is_file():
            continue
        info = read_jar(path)
        if with_sha1:
            info.sha1 = sha1_of(path)
        items.append(info)
    return items


def toggle(mods_dir: Path, filename: str, enabled: bool) -> Path:
    """通过改后缀启停；重名时拒绝。"""
    source = mods_dir / filename
    if not source.is_file():
        raise FileNotFoundError(filename)
    if enabled and filename.endswith(".disabled"):
        target = mods_dir / filename[: -len(".disabled")]
    elif not enabled and filename.endswith(".jar"):
        target = mods_dir / f"{filename}.disabled"
    else:
        return source
    if target.exists():
        raise FileExistsError(target.name)
    source.rename(target)
    return target
