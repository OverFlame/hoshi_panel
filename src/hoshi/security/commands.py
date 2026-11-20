"""控制台命令白名单。

三档：
- strict：只放行原版与额外允许名单里的命令
- extended：strict 再加模组命令常见命名空间（冒号形式）
- raw：不检查，直送 stdin（仅建议在本机模式使用）
"""

from __future__ import annotations

from typing import Literal

Mode = Literal["strict", "extended", "raw"]

VANILLA_COMMANDS = frozenset(
    """
    advance achievement attribute ban ban-ip banlist bossbar clear clone data
    damage debug deop difficulty effect enchant execute experience fill
    fillbiome forceload function gamemode gamerule give help item jfr
    kick kill list locate loot me msg op pardon pardon-ip particle perf
    place playanimation playsound profile publish raid random ready recipe
    reload remove return ride save-all save-off save-on say schedule scoreboard
    seed setblock setidletimeout setworldspawn spawnpoint spectacle spreadplayers
    stop summon tag team teleport tell tellraw tick time title tp transfer
    trigger unban unfreeze warden_warning waypoint weather whitelist worldborder
    xp
    """.split()
)

DANGEROUS = frozenset({"stop", "op", "deop", "ban", "ban-ip", "kick", "reload", "whitelist"})


def normalize(text: str) -> str:
    """去掉换行与前后空格，去掉可选的前导斜杠。"""
    raw = str(text).replace("\r", "").replace("\n", " ").strip()
    if raw.startswith("/"):
        raw = raw[1:].lstrip()
    return raw


def check(text: str, mode: Mode = "strict", extra: list[str] | None = None) -> tuple[bool, str]:
    """返回 (是否放行, 原因)。"""
    command = normalize(text)
    if not command:
        return False, "命令为空"
    if mode == "raw":
        return True, ""

    head = command.split(" ", 1)[0]
    base = head.split(":", 1)[0]
    allowed = set(VANILLA_COMMANDS) | {item.strip().lower() for item in (extra or []) if item.strip()}

    if base in allowed:
        return True, ""
    if mode == "extended" and ":" in head:
        return True, ""
    return False, f"命令不在白名单: {head}"


def requires_confirm(text: str) -> bool:
    """危险命令在界面上要二次确认。"""
    head = normalize(text).split(" ", 1)[0]
    return head.split(":", 1)[0] in DANGEROUS
