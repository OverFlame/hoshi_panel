"""命令行入口：解析参数、加载配置、起服务。

参数优先于配置文件。`--check-config` 只校验不启动，方便改完配置文件先验一遍。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aiohttp import web

from . import APP_NAME, VERSION
from .config import Config, ConfigError, default_path, load, save
from .db import get_meta, record
from .db import init as init_db
from .web import create_app

CLI_MAP = {
    "port": "web.port",
    "bind": "web.bind",
    "data_dir": "app.data_dir",
    "servers_dir": "app.servers_dir",
    "log_level": "app.log_level",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hoshi", description=f"{APP_NAME} 服务端程序")
    parser.add_argument("--config", type=Path, default=None, help="配置文件路径，默认 ./hoshi.toml")
    parser.add_argument("--port", type=str, help="监听端口，覆盖配置文件")
    parser.add_argument("--bind", type=str, help="监听地址，覆盖配置文件")
    parser.add_argument("--data-dir", type=str, dest="data_dir", help="数据目录")
    parser.add_argument("--servers-dir", type=str, dest="servers_dir", help="服务器存放目录")
    parser.add_argument(
        "--log-level", type=str, dest="log_level", help="debug / info / warning / error"
    )
    parser.add_argument("--check-config", action="store_true", help="只校验配置并退出")
    parser.add_argument("--init-config", action="store_true", help="按默认值写出配置文件后退出")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    return parser


def collect_overrides(args: argparse.Namespace) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for attr, key in CLI_MAP.items():
        value = getattr(args, attr, None)
        if value is not None:
            overrides[key] = value
    return overrides


def load_config(args: argparse.Namespace) -> Config:
    path = args.config or default_path()
    return load(path if path.exists() else None, collect_overrides(args))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args)
    except ConfigError as exc:
        for error in exc.errors:
            print(f"配置错误: {error}", file=sys.stderr)
        return 2

    if args.init_config:
        target = save(config, args.config or default_path())
        print(f"已写出配置: {target}")
        return 0

    errors = config.validate()
    if args.check_config:
        for error in errors:
            print(f"校验失败: {error}", file=sys.stderr)
        if not errors:
            print("配置校验通过")
        return 1 if errors else 0

    if errors:
        # 端口之类的问题属于硬错误，直接退出，不要带着错配置起服务
        fatal = [e for e in errors if "web.port" in e or "路径" in e]
        for error in errors:
            print(f"配置警告: {error}", file=sys.stderr)
        if fatal:
            return 2

    data_dir = Path(str(config.get("app.data_dir")))
    db_path = data_dir / "hoshi.db"
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = init_db(db_path)
    record(conn, actor="system", action="start", result="ok", detail=f"v{VERSION}")
    print(
        f"{APP_NAME} {VERSION} · 数据目录 {data_dir} · 配置 {config.path} · "
        f"库 {get_meta(conn, 'schema_version')}"
    )

    app = create_app(config)
    bind = str(config.get("web.bind"))
    port = int(config.get("web.port"))
    print(f"监听 http://{bind}:{port}")
    web.run_app(app, host=bind, port=port, print=None)
    return 0


def run() -> None:  # pragma: no cover - 脚本入口
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
