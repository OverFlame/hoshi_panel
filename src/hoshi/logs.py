"""日志行的级别识别，用于控制台上色。

服务端原始文本不变，只在浏览器端按类别套颜色；这里给出同一套分类，便于测试。
"""

from __future__ import annotations

import re

LEVEL_RE = re.compile(r"/(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\]")
JOIN_RE = re.compile(r"\]: (\S{1,16}) joined the game")
LEAVE_RE = re.compile(r"\]: (\S{1,16}) left the game")
PANEL_PREFIX = "> "

LEVEL_CLASS = {
    "TRACE": "lv-trace",
    "DEBUG": "lv-debug",
    "INFO": "lv-info",
    "WARN": "lv-warn",
    "WARNING": "lv-warn",
    "ERROR": "lv-error",
    "FATAL": "lv-error",
}


def classify(line: str) -> str:
    """返回 CSS 类名：lv-trace / lv-debug / lv-info / lv-warn / lv-error / lv-panel / lv-join / lv-leave。"""
    if line.startswith(PANEL_PREFIX):
        return "lv-panel"
    if JOIN_RE.search(line):
        return "lv-join"
    if LEAVE_RE.search(line):
        return "lv-leave"
    match = LEVEL_RE.search(line)
    if match:
        return LEVEL_CLASS.get(match.group(1), "lv-info")
    lowered = line.lower()
    if "exception" in lowered or "error" in lowered:
        return "lv-error"
    if "warn" in lowered:
        return "lv-warn"
    return "lv-info"


def split_level(line: str) -> tuple[str, str]:
    """返回 (类名, 去掉级别的正文)，正文用于更紧凑的显示；保留原始行给复制用。"""
    return classify(line), line
