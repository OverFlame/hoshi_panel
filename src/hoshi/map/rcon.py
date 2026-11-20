"""最小 RCON 客户端（Source RCON 协议）。

只做三件事：认证、发一条命令、拿回文本。用于查玩家名单与坐标。
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass

TYPE_AUTH = 3
TYPE_AUTH_RESPONSE = 2
TYPE_COMMAND = 2
TYPE_RESPONSE = 0


class RconError(Exception):
    pass


@dataclass
class RconResult:
    ok: bool
    body: str


def encode_packet(request_id: int, packet_type: int, body: str) -> bytes:
    payload = body.encode("utf-8") + b"\x00\x00"
    return struct.pack("<ii", len(payload) + 8, request_id) + struct.pack("<i", packet_type) + payload


def decode_packet(data: bytes) -> tuple[int, int, str]:
    if len(data) < 12:
        raise RconError("包太短")
    size, request_id, packet_type = struct.unpack("<iii", data[:12])
    body = data[12 : size + 4].rstrip(b"\x00").decode("utf-8", "replace")
    return request_id, packet_type, body


async def _read_packet(reader: asyncio.StreamReader) -> tuple[int, int, str]:
    header = await reader.readexactly(4)
    (size,) = struct.unpack("<i", header)
    if size < 10 or size > 1 << 20:
        raise RconError(f"包长度异常: {size}")
    rest = await reader.readexactly(size)
    return decode_packet(header + rest)


async def command(host: str, port: int, password: str, text: str, timeout: float = 5.0) -> RconResult:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (TimeoutError, OSError) as exc:
        raise RconError(f"连不上 RCON: {exc}") from exc

    try:
        writer.write(encode_packet(1, TYPE_AUTH, password))
        await writer.drain()
        request_id, packet_type, _ = await asyncio.wait_for(_read_packet(reader), timeout)
        if packet_type != TYPE_AUTH_RESPONSE or request_id == -1:
            # 有的服端会先回一个空的 RESPONSE_VALUE，再回鉴权结果
            if packet_type == TYPE_RESPONSE:
                request_id, packet_type, _ = await asyncio.wait_for(_read_packet(reader), timeout)
            if request_id == -1:
                return RconResult(False, "RCON 密码错误")
        writer.write(encode_packet(2, TYPE_COMMAND, text))
        await writer.drain()
        _, _, body = await asyncio.wait_for(_read_packet(reader), timeout)
        return RconResult(True, body)
    except TimeoutError as exc:
        raise RconError("RCON 超时") from exc
    except asyncio.IncompleteReadError as exc:
        raise RconError("RCON 连接被关闭") from exc
    finally:
        writer.close()
        with_suppress = getattr(writer, "wait_closed", None)
        if with_suppress:
            try:
                await writer.wait_closed()
            except OSError:
                pass
