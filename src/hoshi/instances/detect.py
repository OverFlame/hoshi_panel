"""从已有目录识别启动方式。

只读目录，不改任何文件。识别不出来就返回 warnings，让调用方要求手填，不要猜。
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

LOADER_PATTERNS = (
    ("forge", re.compile(r"libraries/net/minecraftforge/forge/([^/]+)/(?:win|unix)_args\.txt$")),
    ("neoforge", re.compile(r"libraries/net/neoforged/neoforge/([^/]+)/(?:win|unix)_args\.txt$")),
    (
        "fabric",
        re.compile(r"libraries/net/fabricmc/fabric-loader/([^/]+)/"),
    ),
)


@dataclass
class Detection:
    directory: str
    ok: bool = False
    launch_mode: str = "jar"
    jar: str = ""
    args_file: str = ""
    user_jvm_args: str = ""
    loader: str = ""
    loader_version: str = ""
    mc_version: str = ""
    has_eula: bool = False
    eula_accepted: bool = False
    server_properties: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.ok:
            return "未能识别为 Minecraft 服务端目录"
        parts = [f"方式={self.launch_mode}"]
        if self.jar:
            parts.append(f"核心={self.jar}")
        if self.args_file:
            parts.append(f"参数={self.args_file}")
        if self.loader:
            parts.append(f"加载器={self.loader} {self.loader_version}".strip())
        if self.mc_version:
            parts.append(f"MC={self.mc_version}")
        return " · ".join(parts)


def read_server_properties(root: Path) -> dict[str, str]:
    path = root / "server.properties"
    props: dict[str, str] = {}
    if not path.is_file():
        return props
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        props[key.strip()] = value.strip()
    return props


def _manifest_main_class(jar: Path) -> str:
    try:
        with zipfile.ZipFile(jar) as z:
            text = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    except (KeyError, OSError, zipfile.BadZipFile):
        return ""
    for line in text.splitlines():
        if line.lower().startswith("main-class:"):
            return line.split(":", 1)[1].strip()
    return ""


def find_args_file(root: Path) -> tuple[str, str, str]:
    """返回 (相对路径, loader, 版本)。优先 libraries 下的，其次根目录。"""
    for loader, pattern in LOADER_PATTERNS:
        for candidate in sorted(root.glob("libraries/**/win_args.txt")):
            rel = candidate.relative_to(root).as_posix()
            match = pattern.search(rel)
            if match:
                return rel, loader, match.group(1)
        for candidate in sorted(root.glob("libraries/**/unix_args.txt")):
            rel = candidate.relative_to(root).as_posix()
            match = pattern.search(rel)
            if match:
                return rel, loader, match.group(1)
    if (root / "win_args.txt").is_file():
        return "win_args.txt", "", ""
    return "", "", ""


def find_core_jar(root: Path) -> tuple[str, str]:
    """找根目录里的可启动 jar，返回 (文件名, 警告)。会跳过安装器。"""
    candidates: list[Path] = []
    for jar in sorted(root.glob("*.jar")):
        main = _manifest_main_class(jar)
        if "installer" in main.lower() or "installer" in jar.name.lower():
            continue
        if main:
            candidates.append(jar)
    if not candidates:
        return "", "根目录没有带 Main-Class 的 jar，且没有 args 参数文件"
    candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0].name, ""


def detect(directory: str | Path) -> Detection:
    root = Path(directory).expanduser()
    det = Detection(directory=str(root))
    if not root.is_dir():
        det.warnings.append("目录不存在")
        return det

    det.server_properties = read_server_properties(root)
    eula = root / "eula.txt"
    det.has_eula = eula.is_file()
    if det.has_eula:
        det.eula_accepted = "eula=true" in eula.read_text(encoding="utf-8", errors="replace")

    args_file, loader, version = find_args_file(root)
    if args_file:
        det.launch_mode = "args_file"
        det.args_file = args_file
        det.loader = loader
        det.loader_version = version
        if (root / "user_jvm_args.txt").is_file():
            det.user_jvm_args = "user_jvm_args.txt"
        det.ok = True
    else:
        core, warning = find_core_jar(root)
        if core:
            det.launch_mode = "jar"
            det.jar = core
            det.ok = True
        elif warning:
            det.warnings.append(warning)

    if det.loader_version:
        det.mc_version = det.loader_version.split("-")[0]

    if not det.server_properties:
        det.warnings.append("没有 server.properties，可能不是标准的服端目录")
    if det.ok and not det.has_eula:
        det.warnings.append("没有 eula.txt，首次启动会被服端拒绝")
    return det
