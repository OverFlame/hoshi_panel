"""zip 打包与解包。

导出用 store（jar 与世界本来就压缩过），解包逐条校验路径与符号链接。
"""

from __future__ import annotations

import os
import time
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

from .safe import UnsafePath, resolve_within

DEFAULT_EXCLUDES = {
    "logs",
    "crash-reports",
    "session.lock",
    ".upload",
}

INCLUDE_SETS: dict[str, tuple[str, ...]] = {
    "world": ("world", "world_nether", "world_the_end", "worlds"),
    "config": ("server.properties", "eula.txt", "config", "defaultconfigs", "kubejs", "ops.json"),
    "mods": ("mods", "libraries", "run.bat", "run.sh", "win_args.txt", "user_jvm_args.txt"),
    "logs": ("logs", "crash-reports"),
}


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{num} B"


def iter_files(root: Path, includes: Iterable[str] | None = None) -> Iterator[Path]:
    """按范围收集文件，跳过排除项与符号链接。"""
    base = root.resolve()
    wanted = [item for item in (includes or []) if item]
    seen: set[Path] = set()

    def walk(path: Path) -> Iterator[Path]:
        try:
            entries = list(os.scandir(path))
        except OSError:
            return
        for entry in entries:
            item = Path(entry.path)
            if entry.name in DEFAULT_EXCLUDES:
                continue
            if entry.is_symlink():
                continue
            if entry.is_dir():
                yield from walk(item)
            elif entry.is_file():
                yield item

    if wanted:
        for name in wanted:
            try:
                target = resolve_within(base, name)
            except UnsafePath:
                continue
            if target.is_file():
                candidates = [target]
            elif target.is_dir():
                candidates = list(walk(target))
            else:
                candidates = []
            for item in candidates:
                if item not in seen:
                    seen.add(item)
                    yield item
    else:
        for item in walk(base):
            if item not in seen:
                seen.add(item)
                yield item


def write_zip(
    target: Path,
    root: Path,
    includes: Iterable[str] | None = None,
    chunks: list[Path] | None = None,
) -> int:
    """把文件写进 zip，返回条目数。调用方负责把 target 放在实例目录之外。"""
    count = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for path in chunks if chunks is not None else iter_files(root, includes):
            arcname = path.relative_to(root.resolve()).as_posix()
            archive.write(path, arcname)
            count += 1
    return count


def stream_zip(
    root: Path, includes: Iterable[str] | None = None, cancel_check=None
) -> Iterator[bytes]:
    """边压边发：写到一个临时文件再流式读出，避免整包进内存。"""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        count = write_zip(temp_path, root, includes)
        if count == 0:
            yield b""
            return
        with temp_path.open("rb") as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                yield chunk
    finally:
        temp_path.unlink(missing_ok=True)


def safe_extract(archive_path: Path, destination: Path, progress=None) -> list[str]:
    """解包到目标目录，拒绝越界路径与符号链接，返回跳过的条目。

    progress(done, total) 可选，用来给界面报进度。
    """
    destination.mkdir(parents=True, exist_ok=True)
    skipped: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        total = len(entries)
        for index, info in enumerate(entries, start=1):
            if progress is not None and index % 20 == 0:
                progress(index, total)
            name = info.filename
            if name.endswith("/"):
                continue
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                skipped.append(f"符号链接: {name}")
                continue
            try:
                target = resolve_within(destination, name)
            except UnsafePath:
                skipped.append(f"越界: {name}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open("wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)
        if progress is not None:
            progress(total, total)
    return skipped


def zip_name(prefix: str) -> str:
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}.zip"
