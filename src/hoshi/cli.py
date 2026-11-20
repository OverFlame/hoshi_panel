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
from .db import cleanup as cleanup_audit
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

    totp = sub.add_parser("totp", help="在服务器上直接出动态码（没有验证器 App 时用）")
    totp.add_argument("--config", type=Path, default=None)
    totp.add_argument("--uri", action="store_true", help="打印 otpauth 地址")
    totp.add_argument("--setup", action="store_true", help="在终端里生成密钥并启用，不依赖手机 App")
    totp.add_argument("--disable", action="store_true", help="关闭两步验证")

    codes = sub.add_parser("recovery-codes", help="重新生成一次性恢复码")
    codes.add_argument("--config", type=Path, default=None)

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
        # 配置文件可能还不存在；先占好路径，保存时才写得出去
        config.path = args.config or default_path()
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
    removed = cleanup_audit(conn, keep_days=90)
    if removed:
        print(f"清理过期审计 {removed} 条")

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


def cmd_totp(args: argparse.Namespace) -> int:
    import time

    from .auth import provisioning_uri
    from .auth.totp import STEP, hotp

    config = load_config(args)
    target = args.config or default_path()
    config.path = target

    if args.disable:
        config.set("auth.totp_enabled", False, "cli")
        config.set("auth.totp_secret", "", "cli")
        config.set("auth.recovery_hashes", [], "cli")
        save(config, target)
        print("已关闭两步验证")
        return 0

    if args.setup:
        from .auth import generate_recovery_codes, hash_recovery_codes
        from .auth.totp import STEP, generate_secret, hotp

        secret = generate_secret()
        codes = generate_recovery_codes()
        config.set("auth.totp_secret", secret, "cli")
        config.set("auth.totp_enabled", True, "cli")
        config.set("auth.recovery_hashes", hash_recovery_codes(codes), "cli")
        save(config, target)
        print(f"密钥: {secret}")
        print(f"地址: {provisioning_uri(secret, str(config.get('auth.username')), APP_NAME)}")
        print("恢复码（只显示这一次）：")
        for code in codes:
            print(f"  {code}")
        print(f"当前动态码: {hotp(secret, int(time.time() // STEP))}")
        print(f"已保存到 {target}；以后用 hoshi totp 出码")
        return 0

    secret = str(config.get("auth.totp_secret") or "")
    if not secret:
        print("还没有配置两步验证密钥。没有 App 就在终端运行 hoshi totp --setup", file=sys.stderr)
        return 1
    if args.uri:
        print(provisioning_uri(secret, str(config.get("auth.username")), APP_NAME))
        return 0
    remaining = STEP - int(time.time()) % STEP
    print(f"当前动态码: {hotp(secret, int(time.time() // STEP))}（{remaining} 秒后刷新）")
    return 0


def cmd_recovery_codes(args: argparse.Namespace) -> int:
    from .auth import generate_recovery_codes, hash_recovery_codes

    config = load_config(args)
    codes = generate_recovery_codes()
    config.set("auth.recovery_hashes", hash_recovery_codes(codes), "cli")
    target = args.config or default_path()
    save(config, target)
    print("新的恢复码（旧的一次性码已失效）：")
    for code in codes:
        print(f"  {code}")
    return 0


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
    if raw and raw[0] in ("-h", "--help"):
        build_parser().print_help()
        return 0
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
    if args.command == "totp":
        return cmd_totp(args)
    if args.command == "recovery-codes":
        return cmd_recovery_codes(args)
    if args.command == "reset-password":
        return cmd_reset_password(args)
    parser.print_help()
    return 2


def run() -> None:  # pragma: no cover - 脚本入口
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
