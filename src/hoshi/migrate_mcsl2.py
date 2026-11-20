"""从旧版 MCSL2 迁移实例。

读取旧目录布局，只登记、不搬文件。运行前建议先 --dry-run 看一遍。

用法：
  hoshi migrate-mcsl2 "D:\\MCSL2" --dry-run
  hoshi migrate-mcsl2 "D:\\MCSL2" --java "C:\\Program Files\\Zulu\\zulu-17\\bin\\java.exe"
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .instances import Instance, InstanceError, InstanceRegistry, detect
from .security import jvmargs

MEMORY_UNITS = {"M": 1, "MB": 1, "G": 1024, "GB": 1024}
ENCODING_MAP = {"utf-8": "utf-8", "utf8": "utf-8", "gbk": "gb18030", "cp936": "gb18030", "gb18030": "gb18030"}


@dataclass
class OldInstance:
    name: str
    directory: Path
    core_file: str = ""
    java_path: str = ""
    min_memory: int = 2048
    max_memory: int = 4096
    jvm_args: list[str] = field(default_factory=list)
    encoding: str = "utf-8"
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "directory": str(self.directory),
            "core_file": self.core_file,
            "java_path": self.java_path,
            "min_memory": self.min_memory,
            "max_memory": self.max_memory,
            "jvm_args": self.jvm_args,
            "encoding": self.encoding,
            "problems": self.problems,
        }


def to_mb(value: object, unit: str) -> int:
    try:
        amount = int(float(value))
    except (TypeError, ValueError):
        return 0
    return amount * MEMORY_UNITS.get(str(unit).upper(), 1)


def normalize_encoding(value: object) -> str:
    return ENCODING_MAP.get(str(value or "").strip().lower(), "utf-8")


def scan_mcsl2(root: Path) -> list[OldInstance]:
    servers = root / "Servers" if (root / "Servers").is_dir() else root
    if not servers.is_dir():
        return []
    found: list[OldInstance] = []
    for entry in sorted(servers.iterdir()):
        config_path = entry / "MCSL2ServerConfig.json"
        if not entry.is_dir() or not config_path.is_file():
            continue
        try:
            data = json.loads(config_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue

        unit = str(data.get("memory_unit", "M"))
        old = OldInstance(
            name=str(data.get("name") or entry.name),
            directory=entry,
            core_file=str(data.get("core_file_name", "")),
            java_path=str(data.get("java_path", "")),
            min_memory=to_mb(data.get("min_memory"), unit) or 2048,
            max_memory=to_mb(data.get("max_memory"), unit) or 4096,
            jvm_args=[str(item) for item in (data.get("jvm_arg") or []) if str(item).strip()],
            encoding=normalize_encoding(data.get("output_decoding")),
        )
        if old.jvm_args:
            errors = jvmargs.validate(old.jvm_args)
            if errors:
                old.problems.append("JVM 参数被过滤：" + "; ".join(errors))
                old.jvm_args = [arg for arg in old.jvm_args if not jvmargs.validate([arg])]
        if not old.java_path:
            old.problems.append("旧配置没有 java 路径")
        found.append(old)
    return found


def convert(old: OldInstance, fallback_java: str = "") -> Instance:
    detected = detect(old.directory)
    java = old.java_path or fallback_java
    if not java:
        raise InstanceError("缺少 java 路径，用 --java 指定")

    if detected.launch_mode == "args_file":
        return Instance.new(
            name=old.name,
            directory=str(old.directory),
            launch_mode="args_file",
            args_file=detected.args_file,
            user_jvm_args=detected.user_jvm_args,
            java=java,
            min_memory_mb=old.min_memory,
            max_memory_mb=old.max_memory,
            jvm_args=old.jvm_args,
            encoding=old.encoding,
        )

    core = old.core_file or detected.jar
    if not core:
        raise InstanceError("找不到核心 jar")
    return Instance.new(
        name=old.name,
        directory=str(old.directory),
        launch_mode="jar",
        jar=core,
        java=java,
        min_memory_mb=old.min_memory,
        max_memory_mb=old.max_memory,
        jvm_args=old.jvm_args,
        encoding=old.encoding,
    )


def migrate(
    root: Path,
    registry: InstanceRegistry,
    fallback_java: str = "",
    dry_run: bool = False,
) -> list[dict[str, object]]:
    report: list[dict[str, object]] = []
    for old in scan_mcsl2(root):
        item: dict[str, object] = old.to_dict()
        try:
            instance = convert(old, fallback_java)
        except (InstanceError, FileNotFoundError) as exc:
            item.update({"ok": False, "reason": str(exc)})
            report.append(item)
            continue
        existing = registry.find_by_directory(str(old.directory))
        if existing is not None:
            item.update({"ok": True, "skipped": True, "reason": f"已存在: {existing.name}"})
            report.append(item)
            continue
        if not dry_run:
            registry.add(instance)
        item.update({"ok": True, "skipped": False, "instance_id": instance.id})
        report.append(item)
    return report
