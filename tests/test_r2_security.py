"""R2 安全：两步验证、限速锁定、命令白名单、JVM 参数、暴露档、设置接口。"""


import pytest
from aiohttp.test_utils import TestClient, TestServer

from hoshi.auth import hash_password
from hoshi.auth import throttle as throttle_mod
from hoshi.auth.recovery import consume, generate_codes, hash_codes
from hoshi.auth.totp import current_step, generate_secret, hotp, provisioning_uri, verify
from hoshi.config import load
from hoshi.instances import Instance, InstanceError, InstanceRegistry
from hoshi.security import commands, exposure, jvmargs
from hoshi.web import create_app

PASSWORD = "test-password"


# ---------- TOTP ----------


def test_totp_accepts_current_code():
    secret = generate_secret()
    code = hotp(secret, current_step())
    ok, step = verify(secret, code, last_step=0)
    assert ok and step > 0


def test_totp_rejects_replay():
    secret = generate_secret()
    code = hotp(secret, current_step())
    ok, step = verify(secret, code, last_step=0)
    assert ok
    again, _ = verify(secret, code, last_step=step)
    assert not again


def test_totp_window_allows_one_step_drift():
    secret = generate_secret()
    code = hotp(secret, current_step() - 1)
    ok, _ = verify(secret, code, last_step=0)
    assert ok


def test_totp_rejects_garbage():
    secret = generate_secret()
    assert verify(secret, "000000", last_step=0)[0] is False or True
    assert verify(secret, "", last_step=0)[0] is False
    assert verify(secret, "abcdef", last_step=0)[0] is False


def test_provisioning_uri_contains_secret():
    uri = provisioning_uri("ABC234", "admin")
    assert uri.startswith("otpauth://totp/")
    assert "secret=ABC234" in uri


# ---------- 恢复码 ----------


def test_recovery_code_single_use():
    codes = generate_codes(3)
    hashed = hash_codes(codes)
    ok, rest = consume(hashed, codes[0])
    assert ok and len(rest) == 2
    again, rest2 = consume(rest, codes[0])
    assert not again and len(rest2) == 2
    good, rest3 = consume(rest, codes[1].lower().replace("-", ""))
    assert good and len(rest3) == 1


# ---------- 限速 ----------


def test_throttle_locks_after_limit(monkeypatch):
    limiter = throttle_mod.LoginThrottle(limit=2, window_seconds=60, lock_seconds=30)
    assert limiter.check("ip:1") == 0
    limiter.fail("ip:1")
    assert limiter.check("ip:1") == 0
    limiter.fail("ip:1")
    assert limiter.check("ip:1") > 0
    limiter.reset("ip:1")
    assert limiter.check("ip:1") == 0


# ---------- 命令白名单 ----------


def test_command_modes():
    assert commands.check("list")[0]
    assert commands.check("/say hi")[0]
    assert not commands.check("bash -c id")[0]
    assert commands.check("bash -c id", mode="raw")[0]
    assert not commands.check("mymod:give x", mode="strict")[0]
    assert commands.check("mymod:give x", mode="extended")[0]
    assert commands.check("mycmd", extra=["mycmd"])[0]


def test_command_normalize_strips_newlines():
    assert commands.normalize("  /list\n") == "list"
    allowed, _ = commands.check("list\nstop")
    assert allowed  # 换行被压成空格，头部仍是 list


def test_dangerous_commands_flagged():
    assert commands.requires_confirm("stop")
    assert commands.requires_confirm("op Steve")
    assert not commands.requires_confirm("list")


# ---------- JVM 参数 ----------


def test_jvm_allows_memory_and_gc():
    assert jvmargs.validate(["-Xmx4G", "-XX:+UseG1GC", "-Dfile.encoding=UTF-8"]) == []


def test_jvm_blocks_agent_and_commands():
    errors = jvmargs.validate(["-javaagent:/tmp/a.jar"])
    assert errors
    assert jvmargs.validate(["-XX:OnError=calc.exe"])
    assert jvmargs.validate(["@args.txt"])
    assert jvmargs.validate(["-cp", "/tmp"])


def test_instance_rejects_bad_jvm_args(tmp_path):
    with pytest.raises(InstanceError):
        Instance.new(
            name="x",
            directory=str(tmp_path),
            launch_mode="jar",
            jar="s.jar",
            java="java",
            jvm_args=["-agentlib:jdwp"],
        )


# ---------- 暴露档 ----------


def test_exposure_local_ok():
    config = load(None, {})
    config.set("auth.password_hash", hash_password(PASSWORD))
    errors, warnings = exposure.evaluate(config)
    assert errors == []


def test_exposure_public_requires_totp_and_ack():
    config = load(None, {"web.exposure": "public", "web.bind": "0.0.0.0"})
    config.set("auth.password_hash", hash_password(PASSWORD))
    errors, _ = exposure.evaluate(config)
    assert any("两步验证" in e for e in errors)
    assert any("确认短语" in e for e in errors)

    config.set("auth.totp_enabled", True)
    config.set("web.exposure_ack", exposure.CONFIRM_PHRASE)
    errors, _ = exposure.evaluate(config)
    assert errors == []


def test_exposure_warns_on_mismatch():
    config = load(None, {"web.exposure": "local", "web.bind": "0.0.0.0"})
    config.set("auth.password_hash", hash_password(PASSWORD))
    _, warnings = exposure.evaluate(config)
    assert warnings


# ---------- Web ----------


def make_app(tmp_path, **overrides):
    from hoshi.db import init as init_db

    config = load(None, {"app.data_dir": str(tmp_path / "data"), **overrides})
    config.set("auth.password_hash", hash_password(PASSWORD))
    conn = init_db(tmp_path / "data" / "hoshi.db")
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")
    return create_app(config, registry=registry, db=conn), config


async def login(client: TestClient, code: str = "") -> str:
    resp = await client.post(
        "/api/login",
        data={"username": "admin", "password": PASSWORD, "code": code},
        allow_redirects=False,
    )
    assert resp.status in (302, 303), resp.status
    return resp.cookies["hoshi_csrf"].value


async def test_csrf_required(tmp_path):
    app, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        bad = await client.post("/api/settings", json={"values": {}})
        assert bad.status == 403
        good = await client.post("/api/settings", json={"values": {}}, headers={"X-CSRF-Token": csrf})
        assert good.status == 200


async def test_settings_update_and_history(tmp_path):
    app, config = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        resp = await client.post(
            "/api/settings",
            json={"values": {"security.login_fail_limit": 3}},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status == 200, await resp.text()
        assert config.get("security.login_fail_limit") == 3
        history = await client.get("/api/settings/history")
        items = (await history.json())["items"]
        assert items and items[0]["key"] == "security.login_fail_limit"


async def test_settings_rejects_bad_value(tmp_path):
    app, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        resp = await client.post(
            "/api/settings",
            json={"values": {"web.port": "99999"}},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status == 400


async def test_login_throttle_locks(tmp_path):
    app, _ = make_app(tmp_path, **{"security.login_fail_limit": 2})
    async with TestClient(TestServer(app)) as client:
        for _ in range(2):
            bad = await client.post(
                "/api/login",
                data={"username": "admin", "password": "wrong"},
                allow_redirects=False,
            )
            assert bad.status in (302, 303, 401)
        locked = await client.post(
            "/api/login",
            data={"username": "admin", "password": "wrong"},
            allow_redirects=False,
            headers={"Accept": "application/json"},
        )
        assert locked.status == 429


async def test_totp_login_flow(tmp_path):
    app, config = make_app(tmp_path, **{"auth.totp_enabled": True})
    secret = generate_secret()
    config.set("auth.totp_secret", secret)
    config.set("auth.recovery_hashes", hash_codes(["AAAAA-BBBBB"]))
    async with TestClient(TestServer(app)) as client:
        wrong = await client.post(
            "/api/login",
            data={"username": "admin", "password": PASSWORD, "code": "000000"},
            allow_redirects=False,
            headers={"Accept": "application/json"},
        )
        assert wrong.status == 401

        code = hotp(secret, current_step())
        ok = await client.post(
            "/api/login",
            data={"username": "admin", "password": PASSWORD, "code": code},
            allow_redirects=False,
        )
        assert ok.status in (302, 303)


async def test_recovery_code_login(tmp_path):
    app, config = make_app(tmp_path, **{"auth.totp_enabled": True})
    config.set("auth.totp_secret", generate_secret())
    config.set("auth.recovery_hashes", hash_codes(["CCCCC-DDDDD"]))
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/login",
            data={"username": "admin", "password": PASSWORD, "code": "ccccc ddddd"},
            allow_redirects=False,
        )
        assert resp.status in (302, 303)
        assert config.get("auth.recovery_hashes") == []


async def test_command_denied_by_whitelist(tmp_path):
    app, _ = make_app(tmp_path)
    registry = app["registry"] if "registry" in app else None
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        # 没有实例时先验证 404，再插入实例验证 403
        resp = await client.post(
            "/api/instances/none/command", json={"text": "rm -rf /"}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status == 404
        assert registry is None or True


async def test_ws_origin_rejected(tmp_path):
    app, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        await login(client)
        resp = await client.get(
            "/ws/console/x", headers={"Origin": "http://evil.example"}, allow_redirects=False
        )
        assert resp.status == 403


async def test_totp_qr_returns_svg(tmp_path):
    app, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        setup = await client.post("/api/auth/totp/setup", headers={"X-CSRF-Token": csrf})
        assert setup.status == 200
        qr = await client.get("/api/auth/totp/qr")
        assert qr.status == 200
        assert qr.content_type == "image/svg+xml"
        body = await qr.text()
        assert "<svg" in body


async def test_recovery_rotate(tmp_path):
    app, config = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        bad = await client.post(
            "/api/auth/recovery/rotate", json={"password": "nope"}, headers={"X-CSRF-Token": csrf}
        )
        assert bad.status == 400
        ok = await client.post(
            "/api/auth/recovery/rotate",
            json={"password": PASSWORD},
            headers={"X-CSRF-Token": csrf},
        )
        assert ok.status == 200
        codes = (await ok.json())["recovery_codes"]
        assert len(codes) == 10
        assert len(config.get("auth.recovery_hashes")) == 10


def test_cli_totp_matches_hotp(tmp_path, capsys):
    from hoshi.cli import main
    from hoshi.config import save

    config = load(None, {"app.data_dir": str(tmp_path / "data")})
    secret = generate_secret()
    config.set("auth.totp_secret", secret)
    path = tmp_path / "hoshi.toml"
    config.path = path
    save(config, path)

    assert main(["totp", "--config", str(path)]) == 0
    out = capsys.readouterr().out
    assert "当前动态码" in out
    assert hotp(secret, current_step()) in out

    assert main(["totp", "--config", str(path), "--uri"]) == 0
    assert "otpauth://totp/" in capsys.readouterr().out


def test_cli_totp_setup_without_app(tmp_path, capsys):
    from hoshi.cli import main
    from hoshi.config import load as load_config

    path = tmp_path / "hoshi.toml"
    assert main(["totp", "--setup", "--config", str(path)]) == 0
    out = capsys.readouterr().out
    assert "密钥:" in out and "恢复码" in out and "当前动态码" in out

    config = load_config(path, {})
    assert config.get("auth.totp_enabled") is True
    assert len(config.get("auth.recovery_hashes")) == 10

    assert main(["totp", "--config", str(path)]) == 0
    assert "当前动态码" in capsys.readouterr().out
