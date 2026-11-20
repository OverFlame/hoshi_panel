"""命令行入口。

子命令：
  serve                        启动面板（默认）
  instances list|add|detect    实例管理
  java scan                    探测本机 Java
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aiohttp import web

from . import APP_NAME, VERSION
from .auth.bootstrap import INITIAL_PASSWORD_FILE, ensure_admin
from .config import Config, ConfigError, default_path, load, save
from .db import get_meta, record
from .db import init as init_db
from .instances import Instance, InstanceError, InstanceRegistry, detect, probe, scan
from .security import exposure as exposure_mod
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
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="启动面板（默认动作）")
    serve.add_argument("--config", type=Path, default=None)
    serve.add_argument("--port", type=str)
    serve.add_argument("--bind", type=str)
    serve.add_argument("--data-dir", type=str, dest="data_dir")
    serve.add_argument("--servers-dir", type=str, dest="servers_dir")
    serve.add_argument("--log-level", type=str, dest="log_level")
    serve.add_argument("--check-config", action="store_true")
    serve.add_argument("--init-config", action="store_true")

    instances = sub.add_parser("instances", help="实例管理")
    instances_sub = instances.add_subparsers(dest="instances_command", required=True)
    instances_sub.add_parser("list")
    detect_cmd = instances_sub.add_parser("detect", help="只识别目录，不写配置")
    detect_cmd.add_argument("directory")
    add = instances_sub.add_parser("add", help="注册一个已有目录")
    add.add_argument("name")
    add.add_argument("directory")
    add.add_argument("--java", default="")
    add.add_argument("--min-memory", type=int, default=2048)
    add.add_argument("--max-memory", type=int, default=4096)
    add.add_argument("--mode", choices=("auto", "jar", "args_file"), default="auto")
    add.add_argument("--config", type=Path, default=None)
    add.add_argument("--data-dir", type=str, dest="data_dir")

    reset = sub.add_parser("reset-password", help="生成新的管理员密码")
    reset.add_argument("--config", type=Path, default=None)
    reset.add_argument("--data-dir", type=str, dest="data_dir")

    java = sub.add_parser("java", help="Java 探测")
    java.add_argument("action", choices=("scan",))
    java.add_argument("--path", action="append", default=[])
    return parser


def load_config(args: argparse.Namespace) -> Config:
    path = getattr(args, "config", None) or default_path()
    overrides = {
        key: getattr(args, attr)
        for attr, key in CLI_MAP.items()
        if getattr(args, attr, None) is not None
    }
    return load(path if path.exists() else None, overrides)


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        config = load_config(args)
    except ConfigError as exc:
        for error in exc.errors:
            print(f"配置错误: {error}", file=sys.stderr)
        return 2

    if args.init_config:
        print(f"已写出配置: {save(config, args.config or default_path())}")
        return 0

    errors = config.validate()
    exposure_errors, exposure_warnings = exposure_mod.evaluate(config)
    if args.check_config:
        for error in errors + exposure_errors:
            print(f"校验失败: {error}", file=sys.stderr)
        for warning in exposure_warnings:
            print(f"警告: {warning}", file=sys.stderr)
        if not errors and not exposure_errors:
            print("配置校验通过")
        return 1 if (errors or exposure_errors) else 0

    if exposure_errors:
        for error in exposure_errors:
            print(f"拒绝启动: {error}", file=sys.stderr)
        return 2
    for warning in exposure_warnings:
        print(f"警告: {warning}", file=sys.stderr)
    print(f"暴露状态: {exposure_mod.banner(config)}")

    data_dir = Path(str(config.get("app.data_dir")))
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = init_db(data_dir / "hoshi.db")
    record(conn, actor="system", action="start", result="ok", detail=f"v{VERSION}")

    password = ensure_admin(config, data_dir)
    registry = InstanceRegistry(data_dir / "instances.json")

    print(f"{APP_NAME} {VERSION} · 数据目录 {data_dir} · 配置 {config.path}")
    print(f"实例 {len(registry.all())} 个 · 库 schema {get_meta(conn, 'schema_version')}")
    if password:
        print("=" * 56)
        print(f"首次启动，已生成管理员密码: {password}")
        print(f"同时写入 {data_dir / INITIAL_PASSWORD_FILE}")
        print("=" * 56)

    app = create_app(config, registry=registry, db=conn)
    bind = str(config.get("web.bind"))
    port = int(config.get("web.port"))
    print(f"监听 http://{bind}:{port}")
    web.run_app(app, host=bind, port=port, print=None)
    return 0


def _registry(args: argparse.Namespace) -> InstanceRegistry:
    config = load_config(args)
    return InstanceRegistry(Path(str(config.get("app.data_dir"))) / "instances.json")


def cmd_instances(args: argparse.Namespace) -> int:
    if args.instances_command == "detect":
        result = detect(args.directory)
        print(result.summary())
        for warning in result.warnings:
            print(f"  警告: {warning}")
        return 0 if result.ok else 1

    if args.instances_command == "list":
        registry = _registry(argparse.Namespace(config=default_path(), data_dir=None))
        for item in registry.all():
            print(f"{item.id}  {item.name:<16} {item.launch_mode:<10} {item.directory}")
        return 0

    if args.instances_command == "add":
        result = detect(args.directory)
        print(result.summary())
        if not result.ok and args.mode == "auto":
            print("识别失败：请用 --mode jar|args_file 手动指定", file=sys.stderr)
            return 1
        mode = args.mode if args.mode != "auto" else result.launch_mode
        java = args.java
        if java:
            info = probe(java)
            if info is None:
                print(f"不是可用的 Java: {java}", file=sys.stderr)
                return 1
            print(f"使用 Java: {info.path} ({info.version})")
        else:
            found = scan()
            if not found:
                print("没有探测到 Java，请用 --java 指定", file=sys.stderr)
                return 1
            java = found[0].path
            print(f"使用 Java: {java} ({found[0].version})")
        instance = Instance.new(
            name=args.name,
            directory=str(Path(args.directory).expanduser().resolve()),
            launch_mode=mode,
            jar=result.jar if mode == "jar" else "",
            args_file=result.args_file if mode == "args_file" else "",
            user_jvm_args=result.user_jvm_args,
            java=java,
            min_memory_mb=args.min_memory,
            max_memory_mb=args.max_memory,
        )
        try:
            _registry(args).add(instance)
        except InstanceError as exc:
            print(f"注册失败: {exc}", file=sys.stderr)
            return 1
        print(f"已注册: {instance.name} ({instance.id})")
        print(f"启动参数: {' '.join(instance.argv())}")
        return 0

    return 2


def cmd_reset_password(args: argparse.Namespace) -> int:
    from .auth import generate_password, hash_password

    config = load_config(args)
    password = generate_password()
    config.set("auth.password_hash", hash_password(password), "cli")
    target = args.config or default_path()
    save(config, target)
    data_dir = Path(str(config.get("app.data_dir")))
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / INITIAL_PASSWORD_FILE).write_text(
        f"用户名: {config.get('auth.username')}\n密码: {password}\n", encoding="utf-8"
    )
    print(f"新密码: {password}")
    print(f"已写入 {data_dir / INITIAL_PASSWORD_FILE}，并保存到 {target}")
    return 0


def cmd_java(args: argparse.Namespace) -> int:
    found = scan(args.path)
    if not found:
        print("没有探测到 Java")
        return 1
    for info in found:
        print(f"{info.version:<14} {info.path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    raw = list(argv if argv is not None else sys.argv[1:])
    if not raw or raw[0].startswith("-"):
        raw = ["serve", *raw]
    parser = build_parser()
    args = parser.parse_args(raw)
    if args.command == "serve":
        return cmd_serve(args)
    if args.command == "instances":
        return cmd_instances(args)
    if args.command == "java":
        return cmd_java(args)
    if args.command == "reset-password":
        return cmd_reset_password(args)
    parser.print_help()
    return 2


def run() -> None:  # pragma: no cover - 脚本入口
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
