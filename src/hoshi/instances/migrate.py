"""实例目录迁移：换盘或整理路径。

流程：预检 → 复制到目标 → 校验大小 → 更新实例记录 → 可选删除源目录。
失败时清理目标目录，实例记录保持原样。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .model import Instance


@dataclass
class MigrationPlan:
    source: Path
    target: Path
    total_bytes: int
    free_bytes: int
    same_volume: bool
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def plan_migration(instance: Instance, target: str, running: bool = False) -> MigrationPlan:
    source = instance.root
    destination = Path(target).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if running:
        errors.append("服务器运行中，先停止再迁移")
    if not source.is_dir():
        errors.append(f"源目录不存在: {source}")
    if destination == source:
        errors.append("目标与源相同")
    if destination.exists():
        errors.append(f"目标已存在: {destination}")
    if destination in source.parents:
        errors.append("目标不能是源目录的父目录")

    same_volume = False
    free = 0
    total = 0
    if source.is_dir() and destination.parent.exists():
        try:
            same_volume = source.drive.lower() == destination.drive.lower()
            free = shutil.disk_usage(destination.parent).free
            total = dir_size(source)
        except OSError as exc:
            errors.append(f"读取磁盘信息失败: {exc}")
        if total and free and free < total * 1.05:
            errors.append(f"目标磁盘空间不足：需要 {total // (1 << 20)} MB，可用 {free // (1 << 20)} MB")
        if same_volume:
            warnings.append("同一分区，实际是改名操作，很快")
    elif not destination.parent.exists():
        errors.append(f"目标的父目录不存在: {destination.parent}")

    return MigrationPlan(source, destination, total, free, same_volume, errors, warnings)


def execute_migration(instance: Instance, plan: MigrationPlan, remove_source: bool = True) -> Path:
    if not plan.ok:
        raise ValueError("; ".join(plan.errors))

    plan.target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if plan.same_volume:
            shutil.move(str(plan.source), str(plan.target))
        else:
            shutil.copytree(plan.source, plan.target, symlinks=True)
            copied = dir_size(plan.target)
            if copied < plan.total:
                raise OSError(f"复制不完整：{copied} < {plan.total}")
            if remove_source:
                shutil.rmtree(plan.source)
    except Exception:
        # 半成品目录不留在目标位置
        if plan.target.exists() and not plan.same_volume:
            shutil.rmtree(plan.target, ignore_errors=True)
        raise

    instance.directory = str(plan.target)
    return plan.target
