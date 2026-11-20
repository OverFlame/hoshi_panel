"""实例备份：本地快照，可列举、可回滚、可删除。

备份文件放在 data/backups/<实例 id>/ 下，不进实例目录，避免被一并打包。
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from ..files import write_zip, zip_name
from .model import Instance


@dataclass
class BackupEntry:
    name: str
    path: Path
    size: int
    created: float

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "size": self.size,
            "created": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.created)),
        }


class BackupManager:
    def __init__(self, base_dir: Path, retention: int = 10) -> None:
        self.base_dir = base_dir
        self.retention = max(1, retention)

    def dir_for(self, instance: Instance) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in instance.name)
        return self.base_dir / safe

    def create(self, instance: Instance, includes: list[str] | None = None) -> BackupEntry:
        target_dir = self.dir_for(instance)
        target_dir.mkdir(parents=True, exist_ok=True)
        name = zip_name("backup")
        path = target_dir / name
        count = write_zip(path, instance.root, includes or ["world", "config", "mods"])
        if count == 0:
            path.unlink(missing_ok=True)
            raise ValueError("没有可备份的文件")
        self.prune(instance)
        stat = path.stat()
        return BackupEntry(name=name, path=path, size=stat.st_size, created=stat.st_mtime)

    def list(self, instance: Instance) -> list[BackupEntry]:
        target_dir = self.dir_for(instance)
        if not target_dir.is_dir():
            return []
        entries = []
        for path in sorted(target_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = path.stat()
            entries.append(BackupEntry(path.name, path, stat.st_size, stat.st_mtime))
        return entries

    def prune(self, instance: Instance) -> list[str]:
        entries = self.list(instance)
        removed = []
        for entry in entries[self.retention :]:
            entry.path.unlink(missing_ok=True)
            removed.append(entry.name)
        return removed

    def restore(self, instance: Instance, name: str) -> Path:
        source = self.dir_for(instance) / name
        if not source.is_file():
            raise FileNotFoundError(name)
        target = instance.root
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target / ".restore.zip")
        return target / ".restore.zip"

    def delete(self, instance: Instance, name: str) -> None:
        path = self.dir_for(instance) / name
        if not path.is_file():
            raise FileNotFoundError(name)
        path.unlink()
