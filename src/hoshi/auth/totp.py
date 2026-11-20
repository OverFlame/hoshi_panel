"""TOTP（RFC 6238），只用标准库。

6 位数字，30 秒步长，HMAC-SHA1。允许前后各一个步长的时钟漂移，并拒绝重放。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

DIGITS = 6
STEP = 30
WINDOW = 1


def generate_secret(length: int = 20) -> str:
    """生成 base32 密钥，去掉填充符，方便手输。"""
    raw = secrets.token_bytes(length)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    padded = secret.strip().upper()
    padded += "=" * (-len(padded) % 8)
    return base64.b32decode(padded)


def hotp(secret: str, counter: int) -> str:
    digest = hmac.new(_decode_secret(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10**DIGITS)).zfill(DIGITS)


def current_step(at: float | None = None) -> int:
    return int((at if at is not None else time.time()) // STEP)


def verify(
    secret: str,
    code: str,
    at: float | None = None,
    last_step: int = -1,
    window: int = WINDOW,
) -> tuple[bool, int]:
    """返回 (是否通过, 命中的步长)。命中的步长必须大于 last_step，否则视为重放。"""
    text = "".join(ch for ch in str(code) if ch.isdigit())
    if len(text) != DIGITS or not secret:
        return False, last_step
    now = current_step(at)
    for offset in range(-window, window + 1):
        step = now + offset
        if hmac.compare_digest(hotp(secret, step), text):
            if step <= last_step:
                return False, last_step
            return True, step
    return False, last_step


def provisioning_uri(secret: str, account: str, issuer: str = "HoshiLauncher") -> str:
    label = urllib.parse.quote(f"{issuer}:{account}")
    params = urllib.parse.urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": STEP,
        }
    )
    return f"otpauth://totp/{label}?{params}"
