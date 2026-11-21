"""生成 BlueMap 的完整配置。

按 BlueMap v5 的默认配置键写全：core、storages/file、webserver、webapp、maps/*.conf。
所有取值来自实例级设置，未设置的用这里的默认值。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DIMENSIONS = {
    "overworld": "minecraft:overworld",
    "nether": "minecraft:the_nether",
    "end": "minecraft:the_end",
}
NAMES = {"overworld": "主世界", "nether": "下界", "end": "末地"}


@dataclass
class MapOptions:
    """一个实例的地图设置，全部有默认值。"""

    accept_download: bool = False
    render_threads: int = 1
    update_cooldown: int = 60
    full_update_interval: int = 1440
    region_file_check_interval: int = 5
    scan_for_mod_resources: bool = True
    metrics: bool = False
    compression: str = "gzip"
    web_port: int = 8100
    hires_enabled: bool = True
    flat_view: bool = True
    free_flight_view: bool = True
    perspective_view: bool = True
    render_radius: int = 0
    remove_caves_below_y: int = 55
    min_inhabited_time: int = 0
    render_edges: bool = True
    edge_light_strength: int = 15
    sky_light: int = 1
    ambient_light: int = 0
    sky_color: str = "#7dabff"
    void_color: str = "#000000"
    default_to_flat_view: bool = False
    extra_maps: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_settings(cls, getter) -> MapOptions:
        """getter(key, default) 返回实例级解析后的值。"""

        def number(key: str, default: int) -> int:
            try:
                return int(getter(key, default))
            except (TypeError, ValueError):
                return default

        def flag(key: str, default: bool) -> bool:
            value = getter(key, default)
            return bool(value)

        return cls(
            accept_download=flag("map.accept_download", False),
            render_threads=max(1, number("map.render_threads", 1)),
            update_cooldown=max(10, number("map.update_cooldown", 60)),
            full_update_interval=max(60, number("map.full_update_interval", 1440)),
            region_file_check_interval=max(1, number("map.region_file_check_interval", 5)),
            scan_for_mod_resources=flag("map.scan_for_mod_resources", True),
            metrics=flag("map.metrics", False),
            compression=str(getter("map.compression", "gzip")),
            web_port=number("map.web_port", 8100),
            hires_enabled=flag("map.hires_enabled", True),
            flat_view=flag("map.flat_view", True),
            free_flight_view=flag("map.free_flight_view", True),
            perspective_view=flag("map.perspective_view", True),
            render_radius=max(0, number("map.render_radius", 0)),
            remove_caves_below_y=number("map.remove_caves_below_y", 55),
            min_inhabited_time=max(0, number("map.min_inhabited_time", 0)),
            render_edges=flag("map.render_edges", True),
            edge_light_strength=max(0, min(15, number("map.edge_light_strength", 15))),
            default_to_flat_view=flag("map.default_to_flat_view", False),
        )


def core_conf(options: MapOptions, data_dir: Path) -> str:
    return f"""# 由 HoshiLauncher 生成，手工修改会被覆盖
accept-download: {str(options.accept_download).lower()}
data: "{str(data_dir).replace(chr(92), '/')}"
render-thread-count: {options.render_threads}
update-cooldown: {options.update_cooldown}
full-update-interval: {options.full_update_interval}
region-file-check-interval: {options.region_file_check_interval}
scan-for-mod-resources: {str(options.scan_for_mod_resources).lower()}
metrics: {str(options.metrics).lower()}
"""


def file_storage_conf(options: MapOptions, webroot: Path) -> str:
    allowed = ("gzip", "zstd", "deflate", "none")
    compression = options.compression if options.compression in allowed else "gzip"
    return f"""# 由 HoshiLauncher 生成
storage-type: file
root: "{str(webroot).replace(chr(92), '/')}"
compression: {compression}
"""


def webserver_conf(options: MapOptions, webroot: Path) -> str:
    return f"""# 由 HoshiLauncher 生成
enabled: true
webroot: "{str(webroot).replace(chr(92), '/')}"
port: {options.web_port}
sse-enabled: true
"""


def webapp_conf(options: MapOptions, webroot: Path) -> str:
    return f"""# 由 HoshiLauncher 生成
enabled: true
webroot: "{str(webroot).replace(chr(92), '/')}"
update-settings-file: true
use-cookies: true
default-to-flat-view: {str(options.default_to_flat_view).lower()}
"""


def render_mask(options: MapOptions) -> str:
    if options.render_radius <= 0:
        return "render-mask: []"
    radius = options.render_radius
    return (
        "render-mask: [\n"
        "  {\n"
        f"    min-x: -{radius}\n"
        f"    max-x: {radius}\n"
        f"    min-z: -{radius}\n"
        f"    max-z: {radius}\n"
        "  }\n"
        "]"
    )


def map_conf(options: MapOptions, map_id: str, world: Path, marker_sets: str = "") -> str:
    dimension = DIMENSIONS.get(map_id, "minecraft:overworld")
    name = NAMES.get(map_id, map_id)
    return f"""# 由 HoshiLauncher 生成
world: "{str(world).replace(chr(92), '/')}"
dimension: "{dimension}"
name: "{name}"
sorting: {0 if map_id == 'overworld' else 10 if map_id == 'nether' else 20}
start-pos: {{ x: 0, z: 0 }}
sky-color: "{options.sky_color}"
void-color: "{options.void_color}"
sky-light: {options.sky_light}
ambient-light: {options.ambient_light}
remove-caves-below-y: {options.remove_caves_below_y}
min-inhabited-time: {options.min_inhabited_time}
{render_mask(options)}
render-edges: {str(options.render_edges).lower()}
edge-light-strength: {options.edge_light_strength}
enable-perspective-view: {str(options.perspective_view).lower()}
enable-flat-view: {str(options.flat_view).lower()}
enable-free-flight-view: {str(options.free_flight_view).lower()}
enable-hires: {str(options.hires_enabled).lower()}
storage: "file"
ignore-missing-light-data: false
marker-sets: {{
{marker_sets}}}
"""


def write_all(
    instance_root: Path,
    data_dir: Path,
    options: MapOptions,
    markers: list[dict[str, Any]] | None = None,
) -> dict[str, Path]:
    """写全套配置，返回写出的文件。"""
    config_dir = instance_root / "config" / "bluemap"
    webroot = data_dir / "bluemap" / "web"
    (config_dir / "maps").mkdir(parents=True, exist_ok=True)
    (config_dir / "storages").mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}
    written["core"] = config_dir / "core.conf"
    written["core"].write_text(core_conf(options, data_dir / "bluemap" / "data"), encoding="utf-8")

    written["storage"] = config_dir / "storages" / "file.conf"
    written["storage"].write_text(file_storage_conf(options, webroot), encoding="utf-8")

    written["webserver"] = config_dir / "webserver.conf"
    written["webserver"].write_text(webserver_conf(options, webroot), encoding="utf-8")

    written["webapp"] = config_dir / "webapp.conf"
    written["webapp"].write_text(webapp_conf(options, webroot), encoding="utf-8")

    for map_id, folder in (("overworld", "world"), ("nether", "world_nether"), ("end", "world_the_end")):
        world = instance_root / folder
        if not world.is_dir():
            if map_id != "overworld":
                continue
        marker_sets = ""
        if markers and map_id == "overworld":
            from .bluemap import marker_set_block

            marker_sets = marker_set_block(markers)
        written[map_id] = config_dir / "maps" / f"{map_id}.conf"
        written[map_id].write_text(map_conf(options, map_id, world, marker_sets), encoding="utf-8")
    return written
