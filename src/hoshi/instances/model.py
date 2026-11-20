"""实例模型：字段、序列化、启动参数拼装。

实例只是「一个目录 + 怎么启动」的描述，不复制文件。真正的服务器目录由用户提供。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

LaunchMode = Literal["jar", "args_file"]


class InstanceError(ValueError):
    """实例配置有问题。"""


@dataclass
class Instance:
    id: str
    name: str
    directory: str
    launch_mode: LaunchMode = "jar"
    jar: str = ""
    args_file: str = ""
    user_jvm_args: str = ""
    java: str = ""
    min_memory_mb: int = 2048
    max_memory_mb: int = 4096
    jvm_args: list[str] = field(default_factory=list)
    encoding: str = "utf-8"
    nogui: bool = True
    # 调试/测试用：覆盖启动程序与参数，正常实例留空
    program: str = ""
    args_override: list[str] = field(default_factory=list)

    # ---------- 构造与序列化 ----------

    @staticmethod
    def new(name: str, directory: str, **kwargs: Any) -> Instance:
        instance = Instance(id=secrets.token_hex(6), name=name, directory=directory, **kwargs)
        instance.validate()
        return instance

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Instance:
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        try:
            instance = cls(**payload)
        except TypeError as exc:
            raise InstanceError(f"实例字段不合法: {exc}") from exc
        instance.validate()
        return instance

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "directory": self.directory,
            "launch_mode": self.launch_mode,
            "jar": self.jar,
            "args_file": self.args_file,
            "user_jvm_args": self.user_jvm_args,
            "java": self.java,
            "min_memory_mb": self.min_memory_mb,
            "max_memory_mb": self.max_memory_mb,
            "jvm_args": list(self.jvm_args),
            "encoding": self.encoding,
            "nogui": self.nogui,
            "program": self.program,
            "args_override": list(self.args_override),
        }

    # ---------- 校验 ----------

    def validate(self) -> None:
        if not self.name.strip():
            raise InstanceError("实例名不能为空")
        if not self.directory.strip():
            raise InstanceError("目录不能为空")
        if self.launch_mode not in ("jar", "args_file"):
            raise InstanceError(f"不支持的启动方式: {self.launch_mode}")
        if self.launch_mode == "jar" and not self.jar:
            raise InstanceError("jar 模式下必须指定核心文件名")
        if self.launch_mode == "args_file" and not self.args_file:
            raise InstanceError("args_file 模式下必须指定参数文件")
        if not self.java:
            raise InstanceError("必须指定 java 可执行文件")
        if self.min_memory_mb <= 0 or self.max_memory_mb <= 0:
            raise InstanceError("内存必须为正数")
        if self.min_memory_mb > self.max_memory_mb:
            raise InstanceError("最小内存不能大于最大内存")
        from ..security import jvmargs

        problems = jvmargs.validate(list(self.jvm_args))
        if problems:
            raise InstanceError("; ".join(problems))

    # ---------- 路径与参数 ----------

    @property
    def root(self) -> Path:
        return Path(self.directory).expanduser().resolve()

    def argv(self) -> list[str]:
        """拼出 JVM 参数。程序本体（java）由 supervisor 单独设置。"""
        args = [
            f"-Xms{self.min_memory_mb}M",
            f"-Xmx{self.max_memory_mb}M",
            *self.jvm_args,
        ]
        if self.launch_mode == "jar":
            args += ["-jar", self.jar]
        else:
            if self.user_jvm_args:
                args.append(f"@{self.user_jvm_args}")
            args.append(f"@{self.args_file}")
        if self.nogui:
            args.append("nogui")
        return args

    def missing_paths(self) -> list[str]:
        """启动前检查：目录、核心或参数文件、java 是否存在。"""
        missing: list[str] = []
        root = self.root
        if not root.is_dir():
            missing.append(f"目录不存在: {root}")
        if self.launch_mode == "jar" and self.jar and not (root / self.jar).is_file():
            missing.append(f"核心不存在: {root / self.jar}")
        if self.launch_mode == "args_file" and self.args_file:
            if not (root / self.args_file).is_file():
                missing.append(f"参数文件不存在: {root / self.args_file}")
        if self.user_jvm_args and not (root / self.user_jvm_args).is_file():
            missing.append(f"用户参数文件不存在: {root / self.user_jvm_args}")
        if self.java and not Path(self.java).is_file():
            missing.append(f"java 不存在: {self.java}")
        return missing

