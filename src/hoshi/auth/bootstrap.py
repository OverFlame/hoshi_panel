"""首次启动的引导：生成管理员密码，写散列与初始密码文件。"""

from __future__ import annotations

import os
from pathlib import Path

from ..config import Config, save
from .passwords import generate_password, hash_password

INITIAL_PASSWORD_FILE = "initial-password.txt"


def ensure_admin(config: Config, data_dir: Path) -> str | None:
    """没有密码就生成一个，返回明文（仅首次）。"""
    if config.get("auth.password_hash"):
        return None

    password = generate_password()
    config.set("auth.password_hash", hash_password(password), "file")
    if config.path is not None:
        save(config, config.path)

    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / INITIAL_PASSWORD_FILE
    path.write_text(
        f"首次登录后请修改密码。\n用户名: {config.get('auth.username')}\n密码: {password}\n",
        encoding="utf-8",
    )
    with _best_effort_chmod(path):
        pass
    return password


class _best_effort_chmod:
    """Windows 上 chmod 基本无效，失败就忽略。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> None:
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def __exit__(self, *_: object) -> None:
        return None

