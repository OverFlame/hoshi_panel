"""地图共享令牌：给只读访问用的签名链接。

HMAC 签名，密钥放在 data/secret.key，链接里带过期时间，不需要登录会话。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from pathlib import Path

TOKEN_SEPARATOR = "."


def load_secret(data_dir: Path) -> bytes:
    path = data_dir / "secret.key"
    if path.is_file():
        return path.read_bytes()
    data_dir.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_bytes(32)
    path.write_bytes(secret)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return secret


def _sign(secret: bytes, payload: str) -> str:
    digest = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def issue(secret: bytes, instance: str, ttl_seconds: int = 86400, label: str = "") -> str:
    expires = int(time.time()) + max(60, ttl_seconds)
    payload = f"{instance}:{expires}:{label}"
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{encoded}{TOKEN_SEPARATOR}{_sign(secret, payload)}"


def verify(secret: bytes, token: str) -> tuple[bool, str]:
    """返回 (是否有效, 实例名或错误原因)。"""
    if TOKEN_SEPARATOR not in token:
        return False, "格式不对"
    encoded, signature = token.split(TOKEN_SEPARATOR, 1)
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        payload = base64.urlsafe_b64decode(padded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False, "无法解码"
    if not hmac.compare_digest(_sign(secret, payload), signature):
        return False, "签名不匹配"
    parts = payload.split(":", 2)
    if len(parts) < 2:
        return False, "内容不完整"
    instance, expires = parts[0], parts[1]
    if int(expires) < int(time.time()):
        return False, "已过期"
    return True, instance
