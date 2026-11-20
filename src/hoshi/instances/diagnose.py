"""日志诊断：把常见崩溃关键字翻成人话。

只做模式匹配，不做猜测。匹配不到就说没发现已知问题。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    (
        "eula",
        r"You need to agree to the EULA|eula=false",
        "没有同意 EULA",
        "把实例目录里的 eula.txt 改成 eula=true，或首次启动时确认",
    ),
    (
        "port",
        r"Address already in use|FAILED TO BIND TO PORT",
        "端口被占用",
        "换 server.properties 里的 server-port，或关掉占用该端口的程序",
    ),
    (
        "java",
        r"UnsupportedClassVersionError|class file version (\d+)",
        "Java 版本与服端不匹配",
        "换 Java 17 或 21；实例设置里的 java 路径要指向对的版本",
    ),
    (
        "memory",
        r"OutOfMemoryError|Java heap space",
        "内存不足",
        "调大实例的最大内存，或减少模组与视距",
    ),
    (
        "missing_dep",
        r"Missing or unsupported mandatory dependencies|Mod ID: '([^']+)'",
        "缺少前置模组",
        "按日志里的 Mod ID 补装前置，或删掉依赖它的模组",
    ),
    (
        "incompatible",
        r"Incompatible mod set|Mod resolution failed|Duplicate mods",
        "模组冲突或重复",
        "检查是否有同一模组的多个版本，或客户端专用模组被装到服务端",
    ),
    (
        "noclass",
        r"NoClassDefFoundError|NoSuchMethodError|ClassNotFoundException",
        "类缺失，通常是模组与版本不配对",
        "核对模组支持的游戏版本与加载器版本",
    ),
    (
        "crash_report",
        r"Crash report saved to|A detailed walkthrough",
        "服务端已生成崩溃报告",
        "看实例目录 crash-reports/ 里最新那份，里面有第一手堆栈",
    ),
    (
        "watchdog",
        r"Watchdog Thread.*Stopping server|Server thread dump",
        "看门狗判定卡死并强停",
        "多为某个维度或实体卡住，看当时的 tick 日志与实体数量",
    ),
)


@dataclass
class Finding:
    code: str
    message: str
    hint: str
    line: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "hint": self.hint, "line": self.line}


def diagnose(lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()
    for line in lines:
        for code, pattern, message, hint in PATTERNS:
            if code in seen:
                continue
            if re.search(pattern, line, re.IGNORECASE):
                seen.add(code)
                findings.append(Finding(code=code, message=message, hint=hint, line=line.strip()[:200]))
    return findings
