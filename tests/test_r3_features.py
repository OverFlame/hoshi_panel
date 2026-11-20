"""R3 第二批：模组、属性编辑、迁移、bot 接口。"""

import io
import json
import zipfile
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from hoshi.auth import hash_password
from hoshi.config import load
from hoshi.instances import Instance, InstanceRegistry
from hoshi.instances.properties import Properties
from hoshi.web import create_app

PASSWORD = "test-password"


def fabric_jar(env: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "fabric.mod.json",
            json.dumps({"id": "demo", "name": "Demo Mod", "version": "1.0.0", "environment": env}),
        )
    return buffer.getvalue()


def make_app(tmp_path, **overrides):
    from hoshi.db import init as init_db

    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "servers").mkdir(exist_ok=True)
    config = load(
        None,
        {
            "app.data_dir": str(tmp_path / "data"),
            "app.servers_dir": str(tmp_path / "servers"),
            **overrides,
        },
    )
    config.set("auth.password_hash", hash_password(PASSWORD))
    conn = init_db(tmp_path / "data" / "hoshi.db")
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")

    root = tmp_path / "server"
    (root / "mods").mkdir(parents=True, exist_ok=True)
    (root / "mods" / "client-mod.jar").write_bytes(fabric_jar("client"))
    (root / "mods" / "both-mod.jar").write_bytes(fabric_jar("*"))
    (root / "mods" / "off.jar.disabled").write_bytes(fabric_jar("*"))
    (root / "server.properties").write_text(
        "#Minecraft server properties\n#comment\nlevel-name=world\nserver-port=25565\n",
        encoding="utf-8",
    )
    (root / "server.jar").write_bytes(b"")
    instance = Instance.new(
        name="测试服",
        directory=str(root),
        launch_mode="jar",
        jar="server.jar",
        java="java",
        min_memory_mb=512,
        max_memory_mb=512,
    )
    registry.add(instance)
    return create_app(config, registry=registry, db=conn), config, registry, instance, root


async def login(client: TestClient) -> str:
    resp = await client.post(
        "/api/login", data={"username": "admin", "password": PASSWORD}, allow_redirects=False
    )
    assert resp.status in (302, 303)
    return resp.cookies["hoshi_csrf"].value


def h(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


# ---------- properties ----------


def test_properties_roundtrip_preserves_comments(tmp_path):
    path = tmp_path / "server.properties"
    path.write_text("# head\nlevel-name=world\nmotd=hi\n", encoding="utf-8")
    props = Properties.load(path)
    props.set("motd", "你好")
    props.set("new-key", "1")
    text = props.to_text()
    assert "# head" in text
    assert "motd=你好" in text
    assert "new-key=1" in text
    assert props.get("level-name") == "world"


async def test_properties_api(tmp_path):
    app, _, _, instance, root = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        got = await client.get(f"/api/instances/{instance.id}/properties")
        assert got.status == 200
        body = await got.json()
        assert body["read_only"] is False
        assert any(entry["key"] == "level-name" for entry in body["entries"])

        put = await client.put(
            f"/api/instances/{instance.id}/properties",
            json={"values": {"motd": "新欢迎语"}},
            headers=h(csrf),
        )
        assert put.status == 200
        assert "motd=新欢迎语" in (root / "server.properties").read_text(encoding="utf-8")
        assert (root / "server.properties.bak").exists()


# ---------- 模组 ----------


async def test_mods_list_and_toggle(tmp_path):
    app, _, _, instance, root = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        listing = await client.get(f"/api/instances/{instance.id}/mods")
        assert listing.status == 200
        data = await listing.json()
        by_name = {item["file"]: item for item in data["mods"]}
        assert by_name["client-mod.jar"]["side"] == "client"
        assert by_name["both-mod.jar"]["side"] == "both"
        assert by_name["off.jar.disabled"]["enabled"] is False
        assert data["summary"]["total"] == 3

        off = await client.post(
            f"/api/instances/{instance.id}/mods/toggle",
            json={"file": "both-mod.jar", "enabled": False},
            headers=h(csrf),
        )
        assert off.status == 200
        assert (root / "mods" / "both-mod.jar.disabled").exists()

        on = await client.post(
            f"/api/instances/{instance.id}/mods/toggle",
            json={"file": "off.jar.disabled", "enabled": True},
            headers=h(csrf),
        )
        assert on.status == 200
        assert (root / "mods" / "off.jar").exists()


# ---------- 迁移 ----------


async def test_migrate_instance(tmp_path):
    app, _, registry, instance, root = make_app(tmp_path)
    target = tmp_path / "moved"
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        resp = await client.post(
            f"/api/instances/{instance.id}/migrate",
            json={"target": str(target), "remove_source": True},
            headers=h(csrf),
        )
        assert resp.status == 200, await resp.text()
        body = await resp.json()
        assert Path(body["directory"]) == target.resolve()
        assert (target / "server.properties").exists()
        assert not root.exists()
        assert registry.get(instance.id).directory == str(target.resolve())


async def test_migrate_rejects_existing_target(tmp_path):
    app, _, _, instance, _ = make_app(tmp_path)
    target = tmp_path / "exists"
    target.mkdir()
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        resp = await client.post(
            f"/api/instances/{instance.id}/migrate",
            json={"target": str(target)},
            headers=h(csrf),
        )
        assert resp.status == 400


# ---------- bot ----------


async def test_bot_token_flow_and_rate_limit(tmp_path):
    app, config, _, instance, _ = make_app(tmp_path, **{"bot.user_limit": 1})
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        created = await client.post(
            "/api/bot/tokens", json={"group": "123456", "label": "测试群"}, headers=h(csrf)
        )
        assert created.status == 200
        token = (await created.json())["token"]
        assert token.startswith("hoshi_")

        listing = await client.get("/api/bot/tokens")
        assert len((await listing.json())["tokens"]) == 1

    # bot 接口不需要会话，只要 Bearer
    async with TestClient(TestServer(app)) as client:
        bad = await client.get("/api/bot/status", headers={"Authorization": "Bearer nope"})
        assert bad.status == 401

        ok = await client.get(
            "/api/bot/status?format=json",
            headers={"Authorization": f"Bearer {token}", "X-Bot-User": "u1"},
        )
        assert ok.status == 200
        data = await ok.json()
        assert data["instance"] == "测试服"
        assert data["state"] == "stopped"

        limited = await client.get(
            "/api/bot/status",
            headers={"Authorization": f"Bearer {token}", "X-Bot-User": "u1"},
        )
        assert limited.status == 429
        assert "Retry-After" in limited.headers

        other_user = await client.get(
            "/api/bot/status?format=text",
            headers={"Authorization": f"Bearer {token}", "X-Bot-User": "u2"},
        )
        assert other_user.status == 200
        assert "测试服" in await other_user.text()


async def test_bot_token_revoke(tmp_path):
    app, _, _, _, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        created = await client.post("/api/bot/tokens", json={"group": "g1"}, headers=h(csrf))
        body = await created.json()
        revoked = await client.delete(f"/api/bot/tokens/{body['id']}", headers=h(csrf))
        assert revoked.status == 200
        after = await client.get(
            "/api/bot/status", headers={"Authorization": f"Bearer {body['token']}"}
        )
        assert after.status == 401


async def test_diagnose_endpoint(tmp_path):
    app, _, _, instance, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        await login(client)
        resp = await client.get(f"/api/instances/{instance.id}/diagnose")
        assert resp.status == 200
        body = await resp.json()
        assert body["findings"] == []
        assert body["lines_scanned"] == 0


def test_diagnose_patterns():
    from hoshi.instances.diagnose import diagnose

    lines = [
        "[Server thread/ERROR]: java.lang.OutOfMemoryError: Java heap space",
        "[Server thread/WARN]: You need to agree to the EULA in order to run the server",
        "[Server thread/ERROR]: java.lang.UnsupportedClassVersionError: class file version 61.0",
    ]
    codes = {item.code for item in diagnose(lines)}
    assert {"memory", "eula", "java"} <= codes


async def test_quick_commands(tmp_path):
    app, _, _, _, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        await login(client)
        resp = await client.get("/api/commands")
        commands = (await resp.json())["commands"]
        assert any(item["command"] == "stop" and item["confirm"] for item in commands)


async def test_instance_settings_patch(tmp_path):
    app, _, registry, instance, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        got = await client.get(f"/api/instances/{instance.id}/settings")
        assert got.status == 200
        body = await got.json()
        assert body["max_memory_mb"] == 512

        patched = await client.patch(
            f"/api/instances/{instance.id}",
            json={
                "java": "C:/Java/jdk17/bin/java.exe",
                "max_memory_mb": 4096,
                "jvm_args": "-XX:+UseG1GC -Xss1M",
            },
            headers=h(csrf),
        )
        assert patched.status == 200, await patched.text()
        saved = registry.get(instance.id)
        assert saved.max_memory_mb == 4096
        assert saved.jvm_args == ["-XX:+UseG1GC", "-Xss1M"]
        assert saved.java.endswith("java.exe")


async def test_instance_settings_rejects_bad_jvm(tmp_path):
    app, _, _, instance, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        resp = await client.patch(
            f"/api/instances/{instance.id}",
            json={"jvm_args": "-javaagent:/tmp/x.jar"},
            headers=h(csrf),
        )
        assert resp.status == 400


async def test_fs_list(tmp_path):
    app, _, _, _, root = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        await login(client)
        drives = await client.get("/api/fs/list")
        assert drives.status == 200
        assert "entries" in await drives.json()

        listing = await client.get(f"/api/fs/list?path={root}")
        body = await listing.json()
        names = {entry["name"] for entry in body["entries"]}
        assert "mods" in names
        assert all(entry["type"] == "dir" for entry in body["entries"])

        with_files = await client.get(f"/api/fs/list?path={root}&files=1&suffix=.jar")
        names2 = {entry["name"] for entry in (await with_files.json())["entries"]}
        assert "server.jar" in names2
