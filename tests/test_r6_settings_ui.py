"""按实例设置、指标接口与概览页。"""

from aiohttp.test_utils import TestClient, TestServer

from hoshi.auth import hash_password
from hoshi.config import load
from hoshi.instances import Instance, InstanceRegistry
from hoshi.instances.settings import effective, resolve
from hoshi.logs import classify
from hoshi.metrics import MetricsSampler
from hoshi.web import create_app

PASSWORD = "test-password"


def make_app(tmp_path):
    from hoshi.db import init as init_db

    (tmp_path / "data").mkdir(exist_ok=True)
    config = load(None, {"app.data_dir": str(tmp_path / "data")})
    config.set("auth.password_hash", hash_password(PASSWORD))
    conn = init_db(tmp_path / "data" / "hoshi.db")
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")
    for name in ("甲服", "乙服"):
        root = tmp_path / name
        (root / "mods").mkdir(parents=True, exist_ok=True)
        (root / "server.jar").write_bytes(b"")
        registry.add(
            Instance.new(
                name=name,
                directory=str(root),
                launch_mode="jar",
                jar="server.jar",
                java="java",
                min_memory_mb=512,
                max_memory_mb=512,
            )
        )
    return create_app(config, registry=registry, db=conn), config, registry


async def login(client: TestClient) -> str:
    resp = await client.post(
        "/api/login", data={"username": "admin", "password": PASSWORD}, allow_redirects=False
    )
    assert resp.status in (302, 303)
    return resp.cookies["hoshi_csrf"].value


def test_resolve_priority(tmp_path):
    from hoshi.config import load as load_config

    config = load_config(None, {"map.enabled": "true"})
    instance = Instance.new(
        name="x", directory=str(tmp_path), launch_mode="jar", jar="s.jar", java="java"
    )
    value, source = resolve(config, instance, "map.enabled")
    assert value is True and source == "global"

    instance.settings["map.enabled"] = False
    value, source = resolve(config, instance, "map.enabled")
    assert value is False and source == "instance"

    assert effective(config, instance)["map.enabled"]["source"] == "instance"


def test_log_classify():
    assert classify("[12:00:00] [Server thread/WARN]: 小心") == "lv-warn"
    assert classify("[12:00:00] [Server thread/ERROR]: 崩了") == "lv-error"
    assert classify("[12:00:00] [Server thread/INFO]: 正常") == "lv-info"
    assert classify("[12:00:00] [Server thread/INFO]: Steve joined the game") == "lv-join"
    assert classify("> list") == "lv-panel"
    assert classify("something Exception happened") == "lv-error"


def test_metrics_sampler():
    sampler = MetricsSampler()
    data = sampler.to_dict({})
    assert data["host"]["total_mb"] > 0
    assert "rss_mb" in data["panel"]
    assert data["host"]["cores"] >= 1


async def test_instance_settings_api(tmp_path):
    app, config, registry = make_app(tmp_path)
    first, second = registry.all()
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        got = await client.get(f"/api/instances/{first.id}/instance-settings")
        assert got.status == 200
        items = {item["key"]: item for item in (await got.json())["items"]}
        assert items["map.enabled"]["source"] == "default"

        patched = await client.patch(
            f"/api/instances/{first.id}/instance-settings",
            json={"values": {"map.enabled": True, "command_mode_typo": 1}},
            headers={"X-CSRF-Token": csrf},
        )
        assert patched.status == 400

        ok = await client.patch(
            f"/api/instances/{first.id}/instance-settings",
            json={"values": {"map.enabled": True}},
            headers={"X-CSRF-Token": csrf},
        )
        assert ok.status == 200, await ok.text()
        assert registry.get(first.id).settings["map.enabled"] is True
        assert registry.get(second.id).settings == {}

        status = await client.get("/api/map/status")
        assert (await status.json())["enabled"] is True

        reset = await client.post(
            f"/api/instances/{first.id}/instance-settings/map.enabled/reset",
            headers={"X-CSRF-Token": csrf},
        )
        assert reset.status == 200
        assert registry.get(first.id).settings == {}


async def test_command_mode_per_instance(tmp_path):
    app, config, registry = make_app(tmp_path)
    first, second = registry.all()
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        await client.patch(
            f"/api/instances/{first.id}/instance-settings",
            json={"values": {"console.command_mode": "raw"}},
            headers={"X-CSRF-Token": csrf},
        )
        # 第一个实例 raw 模式应放行任意命令（进程未启动时返回 409 而不是 403）
        raw = await client.post(
            f"/api/instances/{first.id}/command",
            json={"text": "definitely-not-a-command"},
            headers={"X-CSRF-Token": csrf},
        )
        assert raw.status in (200, 409)

        strict = await client.post(
            f"/api/instances/{second.id}/command",
            json={"text": "definitely-not-a-command"},
            headers={"X-CSRF-Token": csrf},
        )
        assert strict.status == 403


async def test_metrics_and_pages(tmp_path):
    app, _, registry = make_app(tmp_path)
    first = registry.all()[0]
    async with TestClient(TestServer(app)) as client:
        await login(client)
        metrics = await client.get("/api/metrics")
        assert metrics.status == 200
        body = await metrics.json()
        assert body["host"]["total_mb"] > 0

        home = await client.get("/")
        text = await home.text()
        assert home.status == 200
        assert "m-mem" in text and "最近事件" in text

        detail = await client.get(f"/i/{first.id}")
        detail_text = await detail.text()
        assert detail.status == 200
        assert "renderLines" in detail_text
        assert first.name in detail_text
