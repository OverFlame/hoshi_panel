"""R5：旧版 MCSL2 迁移、打包脚本与发布。"""

import json

from hoshi.instances import InstanceRegistry
from hoshi.migrate_mcsl2 import convert, migrate, scan_mcsl2

PASSWORD = "test-password"


def make_old_root(tmp_path, name: str = "旧服", **overrides) -> "object":
    root = tmp_path / "MCSL2"
    server = root / "Servers" / name
    (server / "world").mkdir(parents=True)
    (server / "server.jar").write_bytes(b"")
    (server / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    (server / "server.properties").write_text("level-name=world\n", encoding="utf-8")
    config = {
        "name": name,
        "core_file_name": "server.jar",
        "java_path": "C:/Java/bin/java.exe",
        "min_memory": 2,
        "max_memory": 8,
        "memory_unit": "G",
        "jvm_arg": ["-XX:+UseG1GC"],
        "output_decoding": "gbk",
        "input_encoding": "gbk",
    }
    config.update(overrides)
    (server / "MCSL2ServerConfig.json").write_text(json.dumps(config), encoding="utf-8")
    return root


def test_scan_reads_old_config(tmp_path):
    root = make_old_root(tmp_path)
    items = scan_mcsl2(root)
    assert len(items) == 1
    old = items[0]
    assert old.name == "旧服"
    assert old.min_memory == 2048
    assert old.max_memory == 8192
    assert old.encoding == "gb18030"
    assert old.jvm_args == ["-XX:+UseG1GC"]


def test_scan_filters_dangerous_jvm_args(tmp_path):
    root = make_old_root(tmp_path, jvm_arg=["-XX:+UseG1GC", "-javaagent:/tmp/x.jar"])
    old = scan_mcsl2(root)[0]
    assert old.jvm_args == ["-XX:+UseG1GC"]
    assert any("JVM 参数被过滤" in item for item in old.problems)


def test_convert_and_migrate(tmp_path):
    root = make_old_root(tmp_path)
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")
    report = migrate(root, registry, fallback_java="")
    assert report[0]["ok"] is True
    instance = registry.all()[0]
    assert instance.name == "旧服"
    assert instance.max_memory_mb == 8192
    assert instance.encoding == "gb18030"
    assert instance.launch_mode == "jar"
    assert instance.jar == "server.jar"


def test_migrate_dry_run_does_not_write(tmp_path):
    root = make_old_root(tmp_path)
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")
    report = migrate(root, registry, fallback_java="", dry_run=True)
    assert report[0]["ok"] is True
    assert registry.all() == []


def test_migrate_skips_existing_directory(tmp_path):
    root = make_old_root(tmp_path)
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")
    migrate(root, registry, fallback_java="")
    again = migrate(root, registry, fallback_java="")
    assert again[0]["skipped"] is True
    assert len(registry.all()) == 1


def test_migrate_reports_missing_java(tmp_path):
    root = make_old_root(tmp_path, java_path="")
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")
    report = migrate(root, registry, fallback_java="")
    assert report[0]["ok"] is False
    assert "java" in str(report[0]["reason"]).lower()


def test_convert_falls_back_to_detected_args_file(tmp_path):
    root = make_old_root(tmp_path)
    server = root / "Servers" / "旧服"
    (server / "server.jar").unlink()
    lib = server / "libraries" / "net" / "minecraftforge" / "forge" / "1.20.1-47.3.33"
    lib.mkdir(parents=True)
    (lib / "win_args.txt").write_text("-p x\n", encoding="utf-8")
    old = scan_mcsl2(root)[0]
    instance = convert(old, fallback_java="java")
    assert instance.launch_mode == "args_file"
    assert instance.args_file.endswith("win_args.txt")


async def test_packaging_docs_exist():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("QUICKSTART.md", "packaging/README.md", "packaging/build.ps1", "packaging/build.sh"):
        assert (root / name).is_file(), name
    service = (root / "packaging/systemd/hoshi.service").read_text(encoding="utf-8")
    assert "ExecStart" in service and "ReadWritePaths" in service
