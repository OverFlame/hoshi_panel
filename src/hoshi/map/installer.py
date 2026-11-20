"""BlueMap 的获取：优先 Modrinth，失败可改用镜像。

只下载 jar，放到 data/packages/bluemap/，再复制进实例 mods/。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import aiohttp

MODRINTH_API = "https://api.modrinth.com/v2"
PROJECT = "bluemap"


@dataclass
class Download:
    url: str
    filename: str
    sha1: str = ""
    source: str = "modrinth"


async def resolve_modrinth(mc_version: str, loader: str, timeout: float = 15.0) -> Download | None:
    """按 MC 版本与加载器挑一个 BlueMap 版本。找不到返回 None。"""
    loaders = [loader] if loader in ("forge", "neoforge", "fabric") else ["forge"]
    params = {"loaders": f'["{loaders[0]}"]', "game_versions": f'["{mc_version}"]'}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(
                f"{MODRINTH_API}/project/{PROJECT}/version",
                params=params,
                headers={"User-Agent": "hoshi-panel/0.1"},
            ) as resp:
                if resp.status != 200:
                    return None
                versions = await resp.json()
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return None

    for version in versions or []:
        files = version.get("files") or []
        if not files:
            continue
        primary = next((f for f in files if f.get("primary")), files[0])
        url = primary.get("url")
        if not url:
            continue
        return Download(
            url=url,
            filename=str(primary.get("filename") or f"bluemap-{version.get('version_number', 'x')}.jar"),
            sha1=str((primary.get("hashes") or {}).get("sha1", "")),
        )
    return None


async def download(
    target_dir: Path,
    download: Download,
    progress=None,
    timeout: float = 300.0,
) -> Path:
    """下载到目标目录，校验 sha1（有就给），返回文件路径。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / download.filename
    temp = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha1()
    written = 0
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        async with session.get(download.url, headers={"User-Agent": "hoshi-panel/0.1"}) as resp:
            if resp.status != 200:
                raise OSError(f"下载失败：HTTP {resp.status}")
            total = int(resp.headers.get("Content-Length") or 0)
            with temp.open("wb") as fh:
                async for chunk in resp.content.iter_chunked(1 << 16):
                    fh.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
                    if progress is not None:
                        progress(written, total or written)
    if download.sha1 and digest.hexdigest() != download.sha1:
        temp.unlink(missing_ok=True)
        raise OSError("校验失败：sha1 不匹配")
    temp.replace(target)
    return target
