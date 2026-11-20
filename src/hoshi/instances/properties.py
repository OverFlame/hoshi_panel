"""server.properties 的双向编辑：保留注释与顺序。

解析成有序条目，改值时只动对应行，未改的行原样写回。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Entry:
    key: str
    value: str
    raw: str = ""
    comment: bool = False

    def line(self) -> str:
        if self.comment:
            return self.raw
        return f"{self.key}={self.value}"


@dataclass
class Properties:
    entries: list[Entry] = field(default_factory=list)
    trailing_newline: bool = True

    @classmethod
    def parse(cls, text: str) -> Properties:
        entries: list[Entry] = []
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped:
                entries.append(Entry(key="", value="", raw=raw, comment=True))
            elif stripped.startswith("#") or stripped.startswith("!"):
                entries.append(Entry(key="", value="", raw=raw, comment=True))
            elif "=" in stripped:
                key, value = stripped.split("=", 1)
                entries.append(Entry(key=key.strip(), value=value.strip()))
            else:
                entries.append(Entry(key="", value="", raw=raw, comment=True))
        return cls(entries=entries, trailing_newline=text.endswith("\n"))

    @classmethod
    def load(cls, path: Path) -> Properties:
        return cls.parse(path.read_text(encoding="utf-8", errors="replace"))

    def get(self, key: str, default: str = "") -> str:
        for entry in self.entries:
            if not entry.comment and entry.key == key:
                return entry.value
        return default

    def as_list(self) -> list[dict[str, str]]:
        return [{"key": e.key, "value": e.value} for e in self.entries if not e.comment]

    def set(self, key: str, value: str) -> bool:
        """返回是否新增了一行。"""
        for entry in self.entries:
            if not entry.comment and entry.key == key:
                entry.value = value
                return False
        self.entries.append(Entry(key=key, value=value))
        return True

    def remove(self, key: str) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.comment or e.key != key]
        return len(self.entries) != before

    def to_text(self) -> str:
        body = "\n".join(entry.line() for entry in self.entries)
        return body + ("\n" if self.trailing_newline else "")

    def save(self, path: Path) -> None:
        path.write_text(self.to_text(), encoding="utf-8")
