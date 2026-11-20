"""Java 探测与校验。

只认真正能跑 `-XshowSettings:properties -version` 的可执行文件。路径存在不等于它是 Java。
"""

from __future__ import annotations

import glob
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

VERSION_RE = re.compile(r"java\.version\s*=\s*(\S+)")
HOME_RE = re.compile(r"java\.home\s*=\s*(.+)")
VENDOR_RE = re.compile(r"java\.vendor\s*=\s*(.+)")


@dataclass(frozen=True)
class JavaInfo:
    path: str
    version: str
    vendor: str = ""
    home: str = ""

    @property
    def major(self) -> int:
        parts = self.version.split(".")
        if parts[0] == "1" and len(parts) > 1:
            return int(parts[1]) if parts[1].isdigit() else 0
        return int(parts[0]) if parts[0].isdigit() else 0

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "version": self.version, "vendor": self.vendor, "home": self.home}


def probe(path: str | Path, timeout: float = 10.0) -> JavaInfo | None:
    """跑一次 -version，解析出版本与厂商。不是 Java 就返回 None。"""
    exe = str(path)
    if not Path(exe).is_file():
        return None
    try:
        proc = subprocess.run(
            [exe, "-XshowSettings:properties", "-version"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            creationflags=_no_window(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stderr or "") + (proc.stdout or "")
    version = VERSION_RE.search(text)
    if not version:
        return None
    home = HOME_RE.search(text)
    vendor = VENDOR_RE.search(text)
    return JavaInfo(
        path=exe,
        version=version.group(1).strip(),
        home=home.group(1).strip() if home else "",
        vendor=vendor.group(1).strip() if vendor else "",
    )


def candidates() -> list[str]:
    """常见安装位置。不做全盘扫描，宁可漏也别卡住启动。"""
    found: list[str] = []
    exe_name = "java.exe" if platform.system().lower().startswith("win") else "java"

    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        found.append(str(Path(java_home) / "bin" / exe_name))

    which = shutil.which("java")
    if which:
        found.append(which)

    home = Path.home()
    patterns: list[str] = []
    if platform.system().lower().startswith("win"):
        bases = (
            Path(r"C:\Program Files\Java"),
            Path(r"C:\Program Files\Eclipse Adoptium"),
            Path(r"C:\Program Files\Microsoft"),
            Path(r"C:\Program Files\Zulu"),
            Path(r"C:\Program Files\Amazon Corretto"),
            home / ".jdks",
            home / "AppData" / "Roaming" / ".minecraft" / "runtime",
        )
        for base in bases:
            patterns.append(str(base / "*" / "bin" / exe_name))
            patterns.append(str(base / "*" / "*" / "bin" / exe_name))
    else:
        patterns.extend(
            [
                f"/usr/lib/jvm/*/bin/{exe_name}",
                f"/usr/lib/jvm/*/*/bin/{exe_name}",
                f"/opt/*/bin/{exe_name}",
                f"{home}/.jdks/*/bin/{exe_name}",
                f"{home}/.sdkman/candidates/java/*/bin/{exe_name}",
            ]
        )

    for pattern in patterns:
        for match in glob.glob(pattern):
            if Path(match).is_file():
                found.append(match)

    seen: set[str] = set()
    unique: list[str] = []
    for path in found:
        key = str(Path(path).resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


# MC 版本 -> 可用的 Java 主版本区间。乱猜版本是崩溃的常见来源。
JAVA_RANGES: tuple[tuple[str, int, int], ...] = (
    ("1.21", 21, 25),
    ("1.20.5", 21, 25),
    ("1.20", 17, 21),
    ("1.19", 17, 21),
    ("1.18", 17, 21),
    ("1.17", 16, 21),
    ("1.16", 8, 16),
    ("1.15", 8, 15),
    ("1.12", 8, 8),
)


def required_majors(mc_version: str) -> tuple[int, int]:
    """返回 (最小, 最大) 主版本；认不出就给 17 到 21。"""
    text = str(mc_version or "").strip()
    for prefix, low, high in JAVA_RANGES:
        if text.startswith(prefix):
            return low, high
    return 17, 21


def pick_for(mc_version: str, candidates: list[JavaInfo]) -> JavaInfo | None:
    """按 MC 版本挑一个兼容的 Java，优先高版本但不越界。"""
    low, high = required_majors(mc_version)
    fitting = [item for item in candidates if low <= item.major <= high]
    if fitting:
        return max(fitting, key=lambda item: (item.major, item.version))
    return None


def scan(extra: list[str] | None = None) -> list[JavaInfo]:
    """探测所有候选，按版本从高到低排序。"""
    result: dict[str, JavaInfo] = {}
    for path in list(extra or []) + candidates():
        info = probe(path)
        if info:
            result[info.path] = info
    return sorted(result.values(), key=lambda j: (j.major, j.version), reverse=True)


def _no_window() -> int:
    if platform.system().lower().startswith("win"):
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0

