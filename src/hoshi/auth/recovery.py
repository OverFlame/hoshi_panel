"""恢复码：一次性、散列存储、可校验并消费。

只在开启两步验证时生成一次，界面只显示一次。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from .passwords import hash_password, verify_password

COUNT = 10
CODE_BYTES = 5


def _normalize(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def generate_codes(count: int = COUNT) -> list[str]:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(alphabet) for _ in range(CODE_BYTES * 2))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def hash_codes(codes: list[str]) -> list[str]:
    return [hash_password(_normalize(code)) for code in codes]


def consume(codes_hashed: list[str], candidate: str) -> tuple[bool, list[str]]:
    """校验并消费一个恢复码，返回 (是否通过, 剩余散列列表)。"""
    text = _normalize(candidate)
    if not text:
        return False, codes_hashed
    for index, stored in enumerate(codes_hashed):
        if verify_password(text, stored):
            rest = list(codes_hashed)
            rest.pop(index)
            return True, rest
    return False, codes_hashed


def fingerprint(codes: list[str]) -> str:
    """给界面看的前缀提示，不泄露完整码。"""
    if not codes:
        return ""
    joined = ",".join(codes).encode("utf-8")
    return hmac.new(b"hoshi", joined, hashlib.sha256).hexdigest()[:12]
