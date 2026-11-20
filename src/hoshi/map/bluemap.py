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
