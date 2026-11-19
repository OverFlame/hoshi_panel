"""实例注册表：存在 data/instances.json，一次读写整个文件。

规模是「个人服」，几个到几十个实例，不需要数据库。
"""

from __future__ import annotations

import json
from pathlib import Path

from .model import Instance, InstanceError


class InstanceNotFound(KeyError):
    pass


class InstanceRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._items: list[Instance] = []
        self.load()

    # ---------- 读写 ----------

    def load(self) -> list[Instance]:
        if not self.path.is_file():
            self._items = []
            return self._items
        raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        items = []
        for entry in raw.get("instances", []):
            try:
                items.append(Instance.from_dict(entry))
            except InstanceError:
                continue
        self._items = items
        return self._items

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "instances": [i.to_dict() for i in self._items]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ---------- 查询 ----------

    def all(self) -> list[Instance]:
        return list(self._items)

    def get(self, instance_id: str) -> Instance:
        for item in self._items:
            if item.id == instance_id or item.name == instance_id:
                return item
        raise InstanceNotFound(instance_id)

    def find_by_directory(self, directory: str) -> Instance | None:
        target = str(Path(directory).expanduser().resolve()).lower()
        for item in self._items:
            if str(item.root).lower() == target:
                return item
        return None

    # ---------- 变更 ----------

    def add(self, instance: Instance) -> Instance:
        instance.validate()
        if self.find_by_directory(instance.directory):
            raise InstanceError(f"该目录已被注册: {instance.directory}")
        if any(i.name == instance.name for i in self._items):
            raise InstanceError(f"实例名已存在: {instance.name}")
        self._items.append(instance)
        self.save()
        return instance

    def update(self, instance: Instance) -> Instance:
        instance.validate()
        for index, item in enumerate(self._items):
            if item.id == instance.id:
                self._items[index] = instance
                self.save()
                return instance
        raise InstanceNotFound(instance.id)

    def remove(self, instance_id: str) -> None:
        self._items = [i for i in self._items if i.id != instance_id]
        self.save()
