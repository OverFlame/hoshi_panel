
from aiohttp.test_utils import TestClient, TestServer

from hoshi.config import ConfigError, load
from hoshi.web import create_app


def test_defaults_only(tmp_path):
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
    assert 'custom_flag = true' in config.to_toml()


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
    errors = config.validate()
    assert any("web.port" in e for e in errors)


def test_exposure_requires_password():
    config = load(None, {"web.exposure": "public"})
    errors = config.validate()
    assert any("auth.password_hash" in e for e in errors)


def test_toml_round_trip(tmp_path):
    path = tmp_path / "hoshi.toml"
    config = load(None, {"web.port": "26000", "console.extra_commands": "home,spawn"})
    config.path = path
    from hoshi.config import save

    save(config)
    again = load(path, {})
    assert again.get("web.port") == 26000
    assert again.get("console.extra_commands") == ["home", "spawn"]


async def test_health_endpoint(tmp_path):
    config = load(None, {"app.data_dir": str(tmp_path / "data")})
    app = create_app(config)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/health")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["app"] == "HoshiLauncher"


async def test_settings_masks_password(tmp_path):
    config = load(None, {"auth.password_hash": "argon2id$secret"})
    app = create_app(config)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/settings")
        body = await resp.json()
        items = {item["key"]: item for item in body["items"]}
        assert items["auth.password_hash"]["value"] == "***"
        assert items["web.port"]["source"] == "default"


async def test_index_renders(tmp_path):
    config = load(None, {})
    app = create_app(config)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/")
        text = await resp.text()
        assert resp.status == 200
        assert "HoshiLauncher" in text
        assert "web.port" in text


async def test_unknown_path_returns_json(tmp_path):
    config = load(None, {})
    app = create_app(config)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/nope")
        assert resp.status == 404
        body = await resp.json()
        assert body["ok"] is False
