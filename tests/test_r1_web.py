"""R1 集成测试：登录、实例列表、启动停止、控制台 WebSocket。

用 tests/fake_java.py 顶替真 Java，验证链路而不是验证 Minecraft。
"""

import asyncio
import sys
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from hoshi.auth import hash_password
from hoshi.config import load
from hoshi.instances import Instance, InstanceRegistry
from hoshi.instances.supervisor import InstanceProcess
from hoshi.web import create_app

FAKE = Path(__file__).with_name("fake_java.py")
PASSWORD = "test-password"


def make_config(tmp_path):
    config = load(None, {"app.data_dir": str(tmp_path / "data")})
    config.set("auth.password_hash", hash_password(PASSWORD))
    return config


def make_instance(tmp_path) -> Instance:
    root = tmp_path / "server"
    root.mkdir(exist_ok=True)
    (root / "eula.txt").write_text("eula=true", encoding="utf-8")
    (root / "server.jar").write_bytes(b"")  # 占位，只为通过存在性检查
    instance = Instance.new(
        name="香草",
        directory=str(root),
        launch_mode="jar",
        jar="server.jar",
        java=sys.executable,
        min_memory_mb=512,
        max_memory_mb=512,
    )
    # 用覆盖参数跑假 Java，避免真的去启动 Minecraft
    instance.program = sys.executable
    instance.args_override = ["-u", str(FAKE)]
    return instance


async def login(client: TestClient) -> str:
    resp = await client.post(
        "/api/login",
        data={"username": "admin", "password": PASSWORD},
        allow_redirects=False,
    )
    assert resp.status in (302, 303), resp.status
    return resp.cookies["hoshi_csrf"].value


def csrf_headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


async def test_requires_login(tmp_path):
    config = make_config(tmp_path)
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")
    app = create_app(config, registry=registry)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/instances")
        assert resp.status == 401
        page = await client.get("/", allow_redirects=False)
        assert page.status in (302, 303)


async def test_login_and_list(tmp_path):
    config = make_config(tmp_path)
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")
    registry.add(make_instance(tmp_path))
    app = create_app(config, registry=registry)
    async with TestClient(TestServer(app)) as client:
        await login(client)
        resp = await client.get("/api/instances")
        assert resp.status == 200
        data = await resp.json()
        assert data["instances"][0]["name"] == "香草"
        assert data["instances"][0]["state"] == "stopped"


async def test_start_stop_and_console(tmp_path):
    config = make_config(tmp_path)
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")
    instance = registry.add(make_instance(tmp_path))
    app = create_app(config, registry=registry)

    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)

        ws = await client.ws_connect(f"/ws/console/{instance.id}")
        snapshot = await ws.receive_json(timeout=5)
        assert snapshot["type"] == "snapshot"

        start = await client.post(f"/api/instances/{instance.id}/start", headers=csrf_headers(csrf))
        assert start.status == 200, await start.text()

        done = False
        for _ in range(50):
            message = await ws.receive_json(timeout=5)
            if message["type"] == "log" and "Done" in message["line"]:
                done = True
                break
        assert done, "没有等到 Done 输出"

        await client.post(
            f"/api/instances/{instance.id}/command", json={"text": "list"}, headers=csrf_headers(csrf)
        )
        seen_players = False
        for _ in range(50):
            message = await ws.receive_json(timeout=5)
            if message["type"] == "log" and "players online" in message["line"]:
                seen_players = True
                break
        assert seen_players, "没有看到 list 的输出"

        stop = await client.post(f"/api/instances/{instance.id}/stop", headers=csrf_headers(csrf))
        assert stop.status == 200, await stop.text()

        for _ in range(50):
            message = await ws.receive_json(timeout=5)
            if message["type"] == "exit":
                assert message["code"] == 0
                break
        await ws.close()


async def test_stop_when_not_running(tmp_path):
    config = make_config(tmp_path)
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")
    instance = registry.add(make_instance(tmp_path))
    app = create_app(config, registry=registry)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        resp = await client.post(f"/api/instances/{instance.id}/stop", headers=csrf_headers(csrf))
        assert resp.status == 409


async def test_supervisor_ring_buffer(tmp_path):
    instance = make_instance(tmp_path)
    proc = InstanceProcess(instance, tmp_path / "logs")
    result = await proc.start()
    assert result["ok"], result
    for _ in range(100):
        if any("Done" in line for line in proc.snapshot()):
            break
        await asyncio.sleep(0.05)
    assert any("Done" in line for line in proc.snapshot())
    await proc.send("list")
    for _ in range(100):
        if any("players online" in line for line in proc.snapshot()):
            break
        await asyncio.sleep(0.05)
    assert any("players online" in line for line in proc.snapshot())
    assert proc.state == "running"
    await proc.stop()
    assert proc.state == "stopped"
    assert (tmp_path / "logs" / "香草.log").exists()


async def test_crash_state(tmp_path):
    instance = make_instance(tmp_path)
    proc = InstanceProcess(instance, tmp_path / "logs")
    await proc.start()
    await asyncio.sleep(0.2)
    await proc.send("crash")
    for _ in range(100):
        if proc.state == "crashed":
            break
        await asyncio.sleep(0.05)
    assert proc.state == "crashed"
    assert proc.exit_code == 1


@pytest.fixture(autouse=True)
def _no_delay():
    yield


