
from aiohttp.test_utils import TestClient, TestServer

from hoshi.auth import hash_password
from hoshi.config import ConfigError, load
from hoshi.instances import InstanceRegistry
from hoshi.web import create_app

PASSWORD = "test-password"


def make_config(tmp_path, **overrides):
    config = load(None, {"app.data_dir": str(tmp_path / "data"), **overrides})
    config.set("auth.password_hash", hash_password(PASSWORD))
    return config


async def login(client: TestClient):
    resp = await client.post(
        "/api/login",
        data={"username": "admin", "password": PASSWORD},
        allow_redirects=False,
    )
    assert resp.status in (302, 303)
    return resp


# ---------- 配置 ----------


def test_defaults_only():
    config = load(None, {})
    assert config.get("web.port") == 25566
    assert config.source("web.port") == "default"
    assert config.get("web.exposure") == "local"
    assert config.get("map.enabled") is False


def test_file_overrides_default(tmp_path):
    path = tmp_path / "hoshi.toml"
    path.write_text('[web]\nport = 26000\nbind = "0.0.0.0"\n', encoding="utf-8")
    config = load(path, {})
    assert config.get("web.port") == 26000
    assert config.source("web.port") == "file"
    assert config.get("web.bind") == "0.0.0.0"


def test_cli_overrides_file(tmp_path):
    path = tmp_path / "hoshi.toml"
    path.write_text("[web]\nport = 26000\n", encoding="utf-8")
    config = load(path, {"web.port": "27000"})
    assert config.get("web.port") == 27000
    assert config.source("web.port") == "cli"


def test_unknown_keys_are_preserved(tmp_path):
    path = tmp_path / "hoshi.toml"
    path.write_text('[web]\nport = 26000\ncustom_flag = true\n', encoding="utf-8")
    config = load(path, {})
    assert config.extra["web"]["custom_flag"] is True
    assert "custom_flag = true" in config.to_toml()


def test_bad_value_raises(tmp_path):
    path = tmp_path / "hoshi.toml"
    path.write_text('[web]\nport = "abc"\n', encoding="utf-8")
    try:
        load(path, {})
    except ConfigError as exc:
        assert "web.port" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("应当抛出 ConfigError")


def test_validation_flags_out_of_range():
    config = load(None, {"web.port": "70000"})
    assert any("web.port" in e for e in config.validate())


def test_exposure_requires_password():
    config = load(None, {"web.exposure": "public"})
    assert any("auth.password_hash" in e for e in config.validate())


def test_toml_round_trip(tmp_path):
    from hoshi.config import save

    path = tmp_path / "hoshi.toml"
    config = load(None, {"web.port": "26000", "console.extra_commands": "home,spawn"})
    config.path = path
    save(config)
    again = load(path, {})
    assert again.get("web.port") == 26000
    assert again.get("console.extra_commands") == ["home", "spawn"]


# ---------- 接口 ----------


async def test_health_is_public(tmp_path):
    app = create_app(make_config(tmp_path), registry=InstanceRegistry(tmp_path / "data" / "instances.json"))
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/health")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["app"] == "HoshiLauncher"


async def test_settings_requires_login_and_masks_password(tmp_path):
    app = create_app(make_config(tmp_path), registry=InstanceRegistry(tmp_path / "data" / "instances.json"))
    async with TestClient(TestServer(app)) as client:
        assert (await client.get("/api/settings")).status == 401
        await login(client)
        resp = await client.get("/api/settings")
        assert resp.status == 200
        items = {item["key"]: item for item in (await resp.json())["items"]}
        assert items["auth.password_hash"]["value"] == "***"
        assert items["web.port"]["source"] == "default"


async def test_index_requires_login(tmp_path):
    app = create_app(make_config(tmp_path), registry=InstanceRegistry(tmp_path / "data" / "instances.json"))
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/", allow_redirects=False)
        assert resp.status in (302, 303)
        await login(client)
        page = await client.get("/")
        text = await page.text()
        assert page.status == 200
        assert "HoshiLauncher" in text


async def test_unknown_path_returns_json(tmp_path):
    app = create_app(make_config(tmp_path), registry=InstanceRegistry(tmp_path / "data" / "instances.json"))
    async with TestClient(TestServer(app)) as client:
        await login(client)
        resp = await client.get("/nope")
        assert resp.status == 404
        assert (await resp.json())["ok"] is False


async def test_bad_password_rejected(tmp_path):
    app = create_app(make_config(tmp_path), registry=InstanceRegistry(tmp_path / "data" / "instances.json"))
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/login",
            data={"username": "admin", "password": "nope"},
            headers={"Accept": "application/json"},
            allow_redirects=False,
        )
        assert resp.status == 401


async def test_logout_revokes_session(tmp_path):
    app = create_app(make_config(tmp_path), registry=InstanceRegistry(tmp_path / "data" / "instances.json"))
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/login",
            data={"username": "admin", "password": PASSWORD},
            allow_redirects=False,
        )
        csrf = resp.cookies["hoshi_csrf"].value
        assert (await client.get("/api/instances")).status == 200
        await client.post("/api/logout", headers={"X-CSRF-Token": csrf})
        assert (await client.get("/api/instances")).status == 401
