"""BlueMap 接入：版本矩阵、配置生成、启停。

不随仓库分发 jar，启用时按矩阵下载到 data/packages/bluemap/，再复制到实例 mods/。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

VERSION_MATRIX: tuple[tuple[str, str, str], ...] = (
    # (MC 版本前缀, BlueMap 版本, 资产名模板)
    ("1.21", "5.29", "bluemap-{version}-neoforge.jar"),
    ("1.20", "3.20", "bluemap-{version}-forge.jar"),
    ("1.19", "3.20", "bluemap-{version}-forge.jar"),
    ("1.18", "3.20", "bluemap-{version}-forge.jar"),
)

DEFAULT_MC = "1.20.1"


@dataclass
class BlueMapPlan:
    asset: str
    version: str
    webroot: Path
    config_dir: Path
    maps: list[dict[str, str]]


def pick_asset(mc_version: str) -> tuple[str, str]:
    for prefix, version, template in VERSION_MATRIX:
        if mc_version.startswith(prefix):
            return template.format(version=version), version
    return VERSION_MATRIX[-1][2].format(version=VERSION_MATRIX[-1][1]), VERSION_MATRIX[-1][1]


def plan(instance_root: Path, data_dir: Path, mc_version: str = DEFAULT_MC) -> BlueMapPlan:
    asset, version = pick_asset(mc_version)
    webroot = data_dir / "bluemap" / "web"
    config_dir = instance_root / "config" / "bluemap"
    maps: list[dict[str, str]] = []
    for name, world in (
        ("overworld", "world"),
        ("nether", "world_nether"),
        ("end", "world_the_end"),
    ):
        path = instance_root / world
        if path.is_dir():
            maps.append({"id": name, "world": str(path)})
    if not maps:
        maps.append({"id": "overworld", "world": str(instance_root / "world")})
    return BlueMapPlan(asset=asset, version=version, webroot=webroot, config_dir=config_dir, maps=maps)


CORE_CONF = """# 由面板生成，手工改动会被覆盖
accept-download: {accept}
data: "{data}"
webroot: "{webroot}"
render-thread-count: {threads}
metrics: false
update-cooldown: {cooldown}
region-file-check-interval: 30
"""

MAP_CONF = """# 由面板生成
world: "{world}"
dimension: "{dimension}"
name: "{name}"
sorting: 0
start-pos: {{x: 0, z: 0}}
"""

DIMENSIONS = {
    "overworld": "minecraft:overworld",
    "nether": "minecraft:the_nether",
    "end": "minecraft:the_end",
}
NAMES = {"overworld": "主世界", "nether": "下界", "end": "末地"}


def write_config(
    instance_root: Path,
    data_dir: Path,
    mc_version: str = DEFAULT_MC,
    accept_download: bool = False,
    threads: int = 1,
    cooldown: int = 180,
) -> BlueMapPlan:
    result = plan(instance_root, data_dir, mc_version)
    result.config_dir.mkdir(parents=True, exist_ok=True)
    (result.config_dir / "core.conf").write_text(
        CORE_CONF.format(
            accept="true" if accept_download else "false",
            data=str(data_dir / "bluemap" / "data").replace("\\", "/"),
            webroot=str(result.webroot).replace("\\", "/"),
            threads=max(1, threads),
            cooldown=max(30, cooldown),
        ),
        encoding="utf-8",
    )
    maps_dir = result.config_dir / "maps"
    maps_dir.mkdir(exist_ok=True)
    for entry in result.maps:
        (maps_dir / f"{entry['id']}.conf").write_text(
            MAP_CONF.format(
                world=entry["world"].replace("\\", "/"),
                dimension=DIMENSIONS.get(entry["id"], "minecraft:overworld"),
                name=NAMES.get(entry["id"], entry["id"]),
            ),
            encoding="utf-8",
        )
    return result


MARKER_COLORS = {
    "red": "#e05a5a",
    "blue": "#5a8ce0",
    "green": "#4fb477",
    "yellow": "#e0c65a",
    "purple": "#a06ae0",
    "orange": "#e08a4a",
    "white": "#e8e8e8",
}

ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="32" viewBox="0 0 24 32">'
    '<path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 20 12 20s12-11 12-20C24 5.4 18.6 0 12 0z" '
    'fill="{color}" stroke="#00000055" stroke-width="1"/>'
    '<circle cx="12" cy="12" r="4.5" fill="#ffffffcc"/></svg>'
)


def marker_icons_dir(data_dir: Path) -> Path:
    return data_dir / "bluemap" / "web" / "assets"


def write_marker_icons(data_dir: Path) -> None:
    target = marker_icons_dir(data_dir)
    target.mkdir(parents=True, exist_ok=True)
    for name, color in MARKER_COLORS.items():
        (target / f"hoshi-{name}.svg").write_text(ICON_SVG.format(color=color), encoding="utf-8")


def marker_set_block(markers: list[dict[str, object]]) -> str:
    """把标记写成 BlueMap 的 marker-set（HOCON）。没有标记返回空串。"""
    if not markers:
        return ""
    lines = [
        "hoshi-panel: {",
        '  label: "面板标记"',
        "  toggleable: true",
        "  default-hidden: false",
        "  sorting: 100",
        "  markers: {",
    ]
    for marker in markers:
        marker_id = str(marker.get("id", "m"))
        name = str(marker.get("name", "标记")).replace('"', "'")
        note = str(marker.get("note", "")).replace('"', "'").replace("\n", " ")
        color = str(marker.get("color", "red"))
        if color not in MARKER_COLORS:
            color = "red"
        lines.extend(
            [
                f'    "{marker_id}": {{',
                '      type: "poi"',
                f"      position: {{ x: {_num(marker.get('x'))}, y: {_num(marker.get('y'))},"
                f" z: {_num(marker.get('z'))} }}",
                f'      label: "{name}"',
                f'      detail: "{note}"' if note else '      detail: ""',
                f'      icon: "assets/hoshi-{color}.svg"',
                "      anchor: { x: 12, y: 32 }",
                "      sorting: 0",
                "      listed: true",
                "    }",
            ]
        )
    lines.extend(["  }", "}"])
    return "\n".join(lines) + "\n"


def _num(value: object) -> str:
    try:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "0"


def write_markers(instance_root: Path, data_dir: Path, markers: list[dict[str, object]]) -> Path:
    """把标记写进主世界地图配置，并准备图标。返回被改写的文件。"""
    write_marker_icons(data_dir)
    target = instance_root / "config" / "bluemap" / "maps" / "overworld.conf"
    if not target.is_file():
        raise FileNotFoundError("先生成地图配置")
    base = target.read_text(encoding="utf-8")
    # 去掉旧的标记集，再追加，重复调用不会叠加
    base = base.split("\nhoshi-panel: {")[0].rstrip() + "\n"
    target.write_text(base + marker_set_block(markers), encoding="utf-8")
    return target


def find_cached(data_dir: Path, asset: str) -> Path | None:
    candidate = data_dir / "packages" / "bluemap" / asset
    return candidate if candidate.is_file() else None


def install_jar(instance_root: Path, jar: Path) -> Path:
    """复制到实例 mods/，命名保持 bluemap.jar 便于识别。"""
    mods = instance_root / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    target = mods / "bluemap.jar"
    shutil.copy2(jar, target)
    return target


def is_installed(instance_root: Path) -> bool:
    mods = instance_root / "mods"
    return any(mods.glob("bluemap*.jar")) if mods.is_dir() else False
