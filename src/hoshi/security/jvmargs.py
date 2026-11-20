"""JVM 参数白名单。

只放行内存、GC、编码这类常规参数。能执行程序、加载本地库、注入 agent 的一律拒绝。
"""

from __future__ import annotations

BLOCKED_PREFIXES = (
    "-XX:OnError",
    "-XX:OnOutOfMemoryError",
    "-XX:+OnError",
    "-agentpath",
    "-agentlib",
    "-javaagent",
    "-Xbootclasspath",
    "-cp",
    "-classpath",
    "-Djava.system.class.loader",
    "-Dsun.java.command",
)

BLOCKED_PREFIXES_STRICT = ("-Djavax.script", "-Djava.util.logging.config.file", "-Dlog4j")

ALLOWED_PREFIXES = (
    "-Xms",
    "-Xmx",
    "-Xmn",
    "-Xss",
    "-Xss",
    "-XX:+Use",
    "-XX:-Use",
    "-XX:Max",
    "-XX:Min",
    "-XX:Initial",
    "-XX:New",
    "-XX:Survivor",
    "-XX:Metaspace",
    "-XX:+Disable",
    "-XX:+AlwaysPreTouch",
    "-XX:+ParallelRefProc",
    "-XX:G1",
    "-XX:ParallelGCThreads",
    "-XX:ConcGCThreads",
    "-XX:TargetSurvivorRatio",
    "-XX:MaxTenuringThreshold",
    "-XX:+PerfDisableSharedMem",
    "-XX:+HeapDumpOnOutOfMemoryError",
    "-XX:HeapDumpPath",
    "-XX:+ExitOnOutOfMemoryError",
    "-Dfile.encoding",
    "-Duser.language",
    "-Duser.country",
    "-Duser.timezone",
    "-Dfml.",
    "-Dforge.",
    "-Dmixin.",
    "-Dlog4j2.",
    "-Dterminal.",
    "-Djava.awt.headless",
)

MAX_LENGTH = 512
MAX_COUNT = 40


def validate(args: list[str]) -> list[str]:
    """返回错误列表，空表示通过。"""
    errors: list[str] = []
    if len(args) > MAX_COUNT:
        errors.append(f"参数过多：{len(args)} > {MAX_COUNT}")
    for arg in args:
        text = str(arg).strip()
        if not text:
            errors.append("存在空参数")
            continue
        if len(text) > MAX_LENGTH:
            errors.append(f"参数过长：{text[:32]}...")
            continue
        if text.startswith("@"):
            errors.append(f"不接受参数文件：{text}")
            continue
        if any(text.startswith(prefix) for prefix in BLOCKED_PREFIXES):
            errors.append(f"危险参数被拒绝：{text}")
            continue
        if any(text.startswith(prefix) for prefix in BLOCKED_PREFIXES_STRICT) and "file" in text:
            errors.append(f"危险参数被拒绝：{text}")
            continue
        if not any(text.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            errors.append(f"不在允许清单：{text}")
    return errors


def sanitize(args: list[str]) -> list[str]:
    """过滤掉不合规参数，保留合法的。用于历史数据兼容。"""
    return [arg for arg in args if not validate([arg])]
