"""Modrinth 批量查询：用 sha1 反查项目，拿标题与加载器。

一次请求批量提交，失败就当没有，不影响本地结果。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import aiohttp

API = "https://api.modrinth.com/v2"
CACHE_TTL = 7 * 24 * 3600


class ModrinthClient:
    def __init__(self, cache_path: Path | None = None, timeout: float = 8.0) -> None:
        self.cache_path = cache_path
        self.timeout = timeout
        self._cache: dict[str, dict[str, object]] = {}
        self._loaded = False

    # ---------- 缓存 ----------

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.cache_path or not self.cache_path.is_file():
            return
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            now = time.time()
            self._cache = {
                key: value
                for key, value in payload.items()
                if isinstance(value, dict) and now - float(value.get("_ts", 0)) < CACHE_TTL
            }

    def _save(self) -> None:
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, ensure_ascii=False), encoding="utf-8")

    # ---------- 查询 ----------

    async def lookup(self, hashes: list[str]) -> dict[str, dict[str, object]]:
        """返回 sha1 -> {title, side, loaders}。"""
        self._load()
        wanted = [h for h in dict.fromkeys(hashes) if h and h not in self._cache]
        if wanted:
            found = await self._fetch(wanted)
            now = time.time()
            for sha1 in wanted:
                info = found.get(sha1)
                self._cache[sha1] = {**(info or {}), "_ts": now}
            self._save()
        return {h: self._cache[h] for h in hashes if h in self._cache}

    async def _fetch(self, hashes: list[str]) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(
                    f"{API}/version_files",
                    json={"hashes": hashes, "algorithm": "sha1"},
                    headers={"User-Agent": "hoshi-panel/0.1"},
                ) as resp:
                    if resp.status != 200:
                        return result
                    versions = await resp.json()
                project_ids = sorted(
                    {str(v.get("project_id")) for v in versions.values() if v.get("project_id")}
                )
                if not project_ids:
                    return result
                async with session.get(
                    f"{API}/projects",
                    params={"ids": json.dumps(project_ids)},
                    headers={"User-Agent": "hoshi-panel/0.1"},
                ) as resp2:
                    if resp2.status != 200:
                        return result
                    projects = {p["id"]: p for p in await resp2.json()}

            by_hash: dict[str, dict[str, object]] = {}
            for sha1, version in versions.items():
                project = projects.get(str(version.get("project_id")), {})
                side = "both"
                client_side = project.get("client_side")
                server_side = project.get("server_side")
                if client_side == "required" and server_side == "unsupported":
                    side = "client"
                elif server_side == "required" and client_side == "unsupported":
                    side = "server"
                by_hash[sha1] = {
                    "title": project.get("title", ""),
                    "side": side,
                    "loaders": version.get("loaders", []),
                    "slug": project.get("slug", ""),
                }
            return by_hash
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return result


def apply_lookup(mods: list[object], found: dict[str, dict[str, object]]) -> None:
    """把在线结果合进本地扫描结果；在线判定优先于内置名单。"""
    for mod in mods:
        sha1 = getattr(mod, "sha1", "")
        info = found.get(sha1)
        if not info:
            continue
        side = str(info.get("side") or "")
        if side in ("client", "server", "both"):
            mod.side = side
            mod.side_source = "Modrinth"
            mod.advice = "客户端模组，服务端可不装" if side == "client" else (
                "服务端模组" if side == "server" else "两侧都需要"
            )
        if info.get("title") and not mod.name:
            mod.name = str(info["title"])
        loaders = info.get("loaders")
        if isinstance(loaders, list) and loaders:
            mod.loaders = [str(item) for item in loaders]
