"""Windows 上 asyncio 的噪音处理。

浏览器关标签、取消下载、WebSocket 突然断开时，Proactor 事件循环会在回调里抛
ConnectionResetError，默认会把整段 traceback 打到控制台。这类断连不是错误，
静默掉即可；其它异常仍然照常交给默认处理器。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

QUIET_ERRORS = (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)

logger = logging.getLogger("hoshi.asyncio")


def is_disconnect(context: dict[str, object]) -> bool:
    exc = context.get("exception")
    if isinstance(exc, QUIET_ERRORS):
        return True
    message = str(context.get("message", ""))
    handle = context.get("handle")
    return "connection_lost" in message or "connection_lost" in str(handle)


def install_quiet_disconnects(loop: asyncio.AbstractEventLoop) -> None:
    """替换异常处理器：断连静默，其它照旧。"""
    previous = loop.get_exception_handler()

    def handler(active_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
        if is_disconnect(context):
            logger.debug("客户端断连：%s", context.get("message", ""))
            return
        if previous is not None:
            previous(active_loop, context)
        else:
            active_loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


def install_for_running_loop() -> None:
    with contextlib.suppress(RuntimeError):
        install_quiet_disconnects(asyncio.get_running_loop())
