"""标记点：存在 data/markers/<实例>.json，简单 CRUD。"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

COLORS = {"red", "blue", "green", "yellow", "purple", "orange", "white"}


class MarkerStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def _path(self, instance: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in instance)
        return self.base_dir / f"{safe}.json"

    def list(self, instance: str) -> list[dict[str, object]]:
        path = self._path(instance)
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def _save(self, instance: str, items: list[dict[str, object]]) -> None:
        path = self._path(instance)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(
        self,
        instance: str,
        name: str,
        x: float,
        z: float,
        y: float = 64.0,
        color: str = "red",
        note: str = "",
    ) -> dict[str, object]:
        marker = {
            "id": secrets.token_hex(4),
            "name": name.strip() or "标记",
            "x": float(x),
            "y": float(y),
            "z": float(z),
            "color": color if color in COLORS else "red",
            "note": note,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        items = self.list(instance)
        items.append(marker)
        self._save(instance, items)
        return marker

    def remove(self, instance: str, marker_id: str) -> bool:
        items = self.list(instance)
        kept = [item for item in items if item.get("id") != marker_id]
        if len(kept) == len(items):
            return False
        self._save(instance, kept)
        return True
