"""对外暴露的判定。

三档：local 只听本机，lan 允许局域网，public 允许公网。
非 local 需要显式确认短语，public 还要求两步验证已开启。
"""

from __future__ import annotations

from ..config import Config

CONFIRM_PHRASE = "我确认对外开放"
LOCAL_BINDS = {"127.0.0.1", "localhost", "::1", ""}


def is_local_bind(bind: str) -> bool:
    return bind.strip() in LOCAL_BINDS


def evaluate(config: Config) -> tuple[list[str], list[str]]:
    """返回 (阻断错误, 警告)。"""
    errors: list[str] = []
    warnings: list[str] = []

    exposure = str(config.get("web.exposure"))
    bind = str(config.get("web.bind"))
    ack = str(config.get("web.exposure_ack") or "")
    totp = bool(config.get("auth.totp_enabled"))
    password = str(config.get("auth.password_hash") or "")

    # 本机档首次启动会自动生成密码；对外档必须有密码
    if not password and exposure != "local":
        errors.append("未设置管理员密码，无法对外开放")

    if exposure == "local":
        if not is_local_bind(bind):
            warnings.append(
                f"暴露档为 local，但监听地址是 {bind}，实际会对外可达。建议改成 127.0.0.1，或把暴露档调高。"
            )
        return errors, warnings

    if ack != CONFIRM_PHRASE:
        errors.append(f"暴露档为 {exposure}，需要先在设置里填写确认短语：{CONFIRM_PHRASE}")

    if exposure == "public":
        if not totp:
            errors.append("公网档必须先开启两步验证")
        if is_local_bind(bind):
            warnings.append("公网档但监听地址仍是本机地址，外部访问不到")

    if exposure == "lan" and totp is False:
        warnings.append("局域网档未开启两步验证，同网段的设备都能访问登录页")

    return errors, warnings


def banner(config: Config) -> str:
    exposure = str(config.get("web.exposure"))
    if exposure == "public":
        return "对外暴露：公网档，登录页对互联网可见"
    if exposure == "lan":
        return "对外暴露：局域网档，同网段设备可访问"
    return "仅本机可访问"

