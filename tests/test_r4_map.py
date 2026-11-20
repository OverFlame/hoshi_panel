"""R4 地图：RCON、玩家位置、标记、共享链接、BlueMap 配置与反代。"""

import asyncio
import struct

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hoshi.auth import hash_password
from hoshi.config import load
from hoshi.instances import Instance, InstanceRegistry
from hoshi.map import MarkerStore, PlayerPoller, command, find_cached, install_jar, share, write_config
from hoshi.map import rcon as rcon_mod
from hoshi.map.bluemap import pick_asset
from hoshi.web import CONFIG_KEY, create_app

PASSWORD = "test-password"


# ---------- RCON ----------


class FakeRcon:
    def __init__(self, password: str = "secret") -> None:
        self.password = password
        self.server: asyncio.AbstractServer | None = None
        self.port = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                header = await reader.readexactly(4)
                (size,) = struct.unpack("<i", header)
                body = await reader.readexactly(size)
                request_id, packet_type = struct.unpack("<ii", body[:8])
                text = body[8:].rstrip(b"\x00").decode("utf-8", "replace")
                if packet_type == rcon_mod.TYPE_AUTH:
                    ok = text == self.password
                    reply = (request_id if ok else -1, rcon_mod.TYPE_AUTH_RESPONSE, "")
                else:
                    reply = (request_id, rcon_mod.TYPE_RESPONSE, self._answer(text))
                payload = reply[2].encode() + b"\x00\x00"
                writer.write(
                    struct.pack("<ii", len(payload) + 8, reply[0])
                    + struct.pack("<i", reply[1])
                    + payload
                )
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()

    @staticmethod
    def _answer(text: str) -> str:
        if text == "list":
            return "There are 2 of a max of 20 players online: Steve, Alex"
        if text.startswith("data get entity") and "Pos" in text:
            return f"{text.split()[3]} has the following entity data: [10.5d, 64.0d, -20.25d]"
        if text.startswith("data get entity") and "Dimension" in text:
            return f"{text.split()[3]} has the following entity data: \"minecraft:the_nether\""
        return "ok"


async def test_rcon_command_roundtrip():
    server = FakeRcon("secret")
    await server.start()
    try:
        result = await command("127.0.0.1", server.port, "secret", "list")
        assert result.ok
        assert "Steve" in result.body

        bad = await command("127.0.0.1", server.port, "wrong", "list")
        assert not bad.ok
        assert "密码" in bad.body
    finally:
        await server.stop()


async def test_player_poller_parses_positions():
    server = FakeRcon("secret")
    await server.start()
    try:
        poller = PlayerPoller("127.0.0.1", server.port, "secret", interval=1)
        names = await poller.poll_once()
        assert names == ["Steve", "Alex"]
        snapshot = poller.snapshot()
        assert snapshot["connected"] is True
        assert len(snapshot["players"]) == 2
        first = snapshot["players"][0]
        assert first["name"] == "Steve"
        assert first["x"] == 10.5
        assert first["z"] == -20.25
        assert first["dimension"] == "minecraft:the_nether"
    finally:
        await server.stop()


# ---------- 标记 ----------


def test_markers_crud(tmp_path):
    store = MarkerStore(tmp_path)
    marker = store.add("香草", "出生点", 10, -20, 64, "green", "新人集合")
    assert store.list("香草")[0]["name"] == "出生点"
    assert store.remove("香草", marker["id"]) is True
    assert store.list("香草") == []
    assert store.remove("香草", "nope") is False


# ---------- 共享链接 ----------


def test_share_token_roundtrip(tmp_path):
    secret = share.load_secret(tmp_path)
    token = share.issue(secret, "香草", ttl_seconds=60)
    ok, instance = share.verify(secret, token)
    assert ok and instance == "香草"

    other = share.load_secret(tmp_path / "other")
    ok, reason = share.verify(other, token)
    assert not ok and "签名" in reason


def test_share_token_expiry(tmp_path):
    secret = share.load_secret(tmp_path)
    token = share.issue(secret, "香草", ttl_seconds=60)
    ok, _ = share.verify(secret, token, )
    assert ok
    # 手动把过期时间改成过去
    encoded, signature = token.split(".")
    import base64

    payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    instance, _, label = payload.split(":", 2)
    expired_payload = f"{instance}:{0}:{label}"
    encoded2 = base64.urlsafe_b64encode(expired_payload.encode()).decode().rstrip("=")
    forged = f"{encoded2}.{signature}"
    ok2, reason = share.verify(secret, forged)
    assert not ok2


# ---------- BlueMap ----------


def test_pick_asset_matches_mc_version():
    assert pick_asset("1.20.1")[0] == "bluemap-3.20-forge.jar"
    assert "neoforge" in pick_asset("1.21.4")[0]


def test_bluemap_config_uses_existing_worlds(tmp_path):
    root = tmp_path / "server"
    for world in ("world", "world_nether", "world_the_end"):
        (root / world).mkdir(parents=True)
    data_dir = tmp_path / "data"
    result = write_config(root, data_dir, mc_version="1.20.1", accept_download=True, threads=1)
    core = (result.config_dir / "core.conf").read_text(encoding="utf-8")
    assert "accept-download: true" in core
    assert "render-thread-count: 1" in core
    maps = sorted((result.config_dir / "maps").glob("*.conf"))
    assert len(maps) == 3
    nether = (result.config_dir / "maps" / "nether.conf").read_text(encoding="utf-8")
    assert "minecraft:the_nether" in nether
    assert str(root / "world_nether").replace("\\", "/") in nether


def test_install_jar_copies_into_mods(tmp_path):
    root = tmp_path / "server"
    root.mkdir()
    cached = tmp_path / "bluemap-3.20-forge.jar"
    cached.write_bytes(b"stub")
    assert find_cached(tmp_path, "bluemap-3.20-forge.jar") is None
    target = install_jar(root, cached)
    assert target.name == "bluemap.jar"
    assert target.read_bytes() == b"stub"


# ---------- Web 接口 ----------


def make_app(tmp_path, upstream: str = "http://127.0.0.1:1"):
    from hoshi.db import init as init_db

    (tmp_path / "data").mkdir(exist_ok=True)
    for world in ("world", "world_nether", "world_the_end"):
        (tmp_path / "server" / world).mkdir(parents=True, exist_ok=True)
    config = load(
        None,
        {
            "app.data_dir": str(tmp_path / "data"),
            "map.enabled": "true",
            "map.upstream": upstream,
            "map.accept_download": "true",
        },
    )
    config.set("auth.password_hash", hash_password(PASSWORD))
    conn = init_db(tmp_path / "data" / "hoshi.db")
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")
    (tmp_path / "server" / "server.jar").write_bytes(b"")
    (tmp_path / "server" / "server.properties").write_text(
        "enable-rcon=true\nrcon.port=25575\nrcon.password=secret\n", encoding="utf-8"
    )
    instance = Instance.new(
        name="香草",
        directory=str(tmp_path / "server"),
        launch_mode="jar",
        jar="server.jar",
        java="java",
        min_memory_mb=512,
        max_memory_mb=512,
    )
    registry.add(instance)
    return create_app(config, registry=registry, db=conn), instance


async def login(client: TestClient) -> str:
    resp = await client.post(
        "/api/login", data={"username": "admin", "password": PASSWORD}, allow_redirects=False
    )
    assert resp.status in (302, 303)
    return resp.cookies["hoshi_csrf"].value


async def test_map_status_and_config(tmp_path):
    app, instance = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        status = await client.get("/api/map/status")
        assert status.status == 200
        body = await status.json()
        assert body["enabled"] is True
        assert body["instance"] == "香草"
        assert body["plan"]["asset"] == "bluemap-3.20-forge.jar"

        cfg = await client.post(
            f"/api/instances/{instance.id}/map/config",
            json={"mc_version": "1.20.1"},
            headers={"X-CSRF-Token": csrf},
        )
        assert cfg.status == 200
        data = await cfg.json()
        assert data["jar_installed"] is False
        assert (instance.root / "config" / "bluemap" / "core.conf").exists()


async def test_markers_api(tmp_path):
    app, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        created = await client.post(
            "/api/map/markers",
            json={"name": "矿洞", "x": 100, "z": -50, "color": "blue"},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status == 200
        marker_id = (await created.json())["marker"]["id"]

        listed = await client.get("/api/map/markers?instance=香草")
        assert len((await listed.json())["markers"]) == 1

        removed = await client.delete(
            "/api/map/markers?id=" + marker_id, headers={"X-CSRF-Token": csrf}
        )
        assert removed.status == 200


async def test_map_share_and_proxy(tmp_path):
    async def echo(request: web.Request) -> web.Response:
        return web.Response(text=f"map-page:{request.path}")

    upstream = web.Application()
    upstream.router.add_get("/{tail:.*}", echo)
    upstream_server = TestServer(upstream)
    await upstream_server.start_server()
    port = upstream_server.port

    app, _ = make_app(tmp_path, upstream=f"http://127.0.0.1:{port}")
    try:
        async with TestClient(TestServer(app)) as client:
            csrf = await login(client)
            share_resp = await client.post("/api/map/share", json={}, headers={"X-CSRF-Token": csrf})
            assert share_resp.status == 200
            url = (await share_resp.json())["url"]

            page = await client.get(url, allow_redirects=True)
            assert page.status == 200
            assert "map-page" in await page.text()

        # 不带会话，仅带令牌也应可访问
        async with TestClient(TestServer(app)) as anon:
            resp = await anon.get(url)
            assert resp.status == 200
            assert "map-page" in await resp.text()

            bad = await anon.get("/map/?t=forged.token")
            assert bad.status == 403
    finally:
        await upstream_server.close()


async def test_map_disabled_returns_404(tmp_path):
    app, _ = make_app(tmp_path)
    app[CONFIG_KEY].set("map.enabled", False)
    async with TestClient(TestServer(app)) as client:
        await login(client)
        resp = await client.get("/map/")
        assert resp.status == 404


@pytest.mark.parametrize("bad", ["", "abc", "a.b.c"])
def test_share_rejects_garbage(tmp_path, bad):
    secret = share.load_secret(tmp_path)
    ok, _ = share.verify(secret, bad)
    assert not ok


def test_marker_set_block_and_apply(tmp_path):
    from hoshi.map import marker_set_block, write_markers
    from hoshi.map.bluemap import write_config

    root = tmp_path / "server"
    (root / "world").mkdir(parents=True)
    data_dir = tmp_path / "data"
    write_config(root, data_dir, mc_version="1.20.1", accept_download=True)

    marker = {"id": "abc", "name": "出生点", "x": 0, "y": 64, "z": 0, "color": "green", "note": "新人来这"}
    block = marker_set_block([marker])
    assert "hoshi-panel" in block and "assets/hoshi-green.svg" in block
    assert "出生点" in block

    target = write_markers(root, data_dir, [marker])
    text = target.read_text(encoding="utf-8")
    assert text.count("hoshi-panel") == 1
    assert (data_dir / "bluemap" / "web" / "assets" / "hoshi-green.svg").exists()

    # 再写一次不会叠两份
    write_markers(root, data_dir, [marker])
    again = target.read_text(encoding="utf-8")
    assert again.count("hoshi-panel") == 1


async def test_marker_api_writes_bluemap_config(tmp_path):
    from hoshi.map.bluemap import write_config

    app, instance = make_app(tmp_path)
    write_config(instance.root, tmp_path / "data", mc_version="1.20.1", accept_download=True)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        created = await client.post(
            "/api/map/markers",
            json={"name": "矿洞", "x": 12, "z": -34, "color": "blue"},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status == 200
        body = await created.json()
        assert body["bluemap"]["applied"] is True
        conf = (instance.root / "config" / "bluemap" / "maps" / "overworld.conf").read_text(encoding="utf-8")
        assert "矿洞" in conf and "hoshi-blue.svg" in conf


async def test_map_index_injects_overlay(tmp_path):
    async def page(_request: web.Request) -> web.Response:
        return web.Response(text="<html><body>map</body></html>", content_type="text/html")

    upstream = web.Application()
    upstream.router.add_get("/", page)
    upstream.router.add_get("/index.html", page)
    upstream_server = TestServer(upstream)
    await upstream_server.start_server()

    app, _ = make_app(tmp_path, upstream=f"http://127.0.0.1:{upstream_server.port}")
    try:
        async with TestClient(TestServer(app)) as client:
            await login(client)
            resp = await client.get("/map/")
            html = await resp.text()
            assert "/map-overlay.js" in html

            js = await client.get("/map-overlay.js")
            assert js.status == 200
            assert "hoshi-players" in await js.text()
    finally:
        await upstream_server.close()


async def test_overlay_requires_auth(tmp_path):
    app, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as anon:
        resp = await anon.get("/map-overlay.js")
        assert resp.status == 401


async def test_rcon_settings_api(tmp_path):
    app, instance = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        got = await client.get(f"/api/instances/{instance.id}/rcon")
        assert got.status == 200
        body = await got.json()
        assert body["port"] == "25575"

        bad = await client.post(
            f"/api/instances/{instance.id}/rcon",
            json={"enabled": True, "port": 25575, "password": ""},
            headers={"X-CSRF-Token": csrf},
        )
        assert bad.status == 400

        ok = await client.post(
            f"/api/instances/{instance.id}/rcon",
            json={"enabled": True, "port": 25576, "password": "secret2"},
            headers={"X-CSRF-Token": csrf},
        )
        assert ok.status == 200
        props = (instance.root / "server.properties").read_text(encoding="utf-8")
        assert "enable-rcon=true" in props
        assert "rcon.port=25576" in props
        assert "rcon.password=secret2" in props


async def test_map_install_from_mirror(tmp_path):
    payload = b"fake-jar"

    async def jar(_request: web.Request) -> web.Response:
        return web.Response(body=payload, content_type="application/java-archive")

    mirror = web.Application()
    mirror.router.add_get("/bluemap-3.20-forge.jar", jar)
    mirror_server = TestServer(mirror)
    await mirror_server.start_server()

    app, instance = make_app(tmp_path)
    config = app[CONFIG_KEY]
    config.set("map.download_mirror", f"http://127.0.0.1:{mirror_server.port}/bluemap-3.20-forge.jar")
    try:
        async with TestClient(TestServer(app)) as client:
            csrf = await login(client)
            resp = await client.post(
                f"/api/instances/{instance.id}/map/install", headers={"X-CSRF-Token": csrf}
            )
            assert resp.status == 200, await resp.text()
            job_id = (await resp.json())["job"]["id"]
            done = await wait_job(client, job_id, timeout=15)
            assert done["error"] == "", done
            assert (instance.root / "mods" / "bluemap.jar").read_bytes() == payload
    finally:
        await mirror_server.close()


async def wait_job(client, job_id: str, timeout: float = 15.0) -> dict:
    import asyncio

    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        resp = await client.get(f"/api/jobs/{job_id}")
        data = await resp.json()
        if data.get("finished"):
            return data
        await asyncio.sleep(0.05)
    raise AssertionError("job 超时")
