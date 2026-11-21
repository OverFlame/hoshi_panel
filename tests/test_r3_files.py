"""R3：文件管理、导出导入、备份、整合包导入。"""

import asyncio
import io
import zipfile
from pathlib import Path

import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from hoshi.auth import hash_password
from hoshi.config import load
from hoshi.files import UnsafePath, resolve_within
from hoshi.instances import Instance, InstanceRegistry
from hoshi.web import create_app

PASSWORD = "test-password"


def make_app(tmp_path):
    from hoshi.db import init as init_db

    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "servers").mkdir(exist_ok=True)
    config = load(
        None,
        {
            "app.data_dir": str(tmp_path / "data"),
            "app.servers_dir": str(tmp_path / "servers"),
        },
    )
    config.set("auth.password_hash", hash_password(PASSWORD))
    conn = init_db(tmp_path / "data" / "hoshi.db")
    registry = InstanceRegistry(tmp_path / "data" / "instances.json")

    root = tmp_path / "server"
    (root / "world").mkdir(parents=True, exist_ok=True)
    (root / "world" / "level.dat").write_bytes(b"level")
    (root / "server.properties").write_text("level-name=world\n", encoding="utf-8")
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
    return create_app(config, registry=registry, db=conn), config, instance, root


async def login(client: TestClient) -> str:
    resp = await client.post(
        "/api/login",
        data={"username": "admin", "password": PASSWORD},
        allow_redirects=False,
    )
    assert resp.status in (302, 303)
    return resp.cookies["hoshi_csrf"].value


def headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


# ---------- 路径安全 ----------


def test_resolve_within_blocks_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    assert resolve_within(root, "a/b.txt") == (root / "a/b.txt").resolve()
    for bad in ("../x", "a/../../x", "/etc/passwd", "C:/Windows/win.ini"):
        with pytest.raises(UnsafePath):
            resolve_within(root, bad)


# ---------- 文件接口 ----------


async def test_list_and_read_file(tmp_path):
    app, _, instance, root = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        await login(client)
        listing = await client.get(f"/api/instances/{instance.id}/files?path=")
        assert listing.status == 200
        names = {entry["name"] for entry in (await listing.json())["entries"]}
        assert "world" in names and "server.properties" in names

        read = await client.get(f"/api/instances/{instance.id}/file?path=server.properties")
        assert read.status == 200
        assert "level-name" in (await read.json())["content"]

        escape = await client.get(f"/api/instances/{instance.id}/file?path=../secret")
        assert escape.status == 400


async def test_write_and_delete_file(tmp_path):
    app, _, instance, root = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        put = await client.put(
            f"/api/instances/{instance.id}/file",
            json={"path": "config/new.txt", "content": "你好"},
            headers=headers(csrf),
        )
        assert put.status == 200
        assert (root / "config" / "new.txt").read_text(encoding="utf-8") == "你好"

        bad = await client.put(
            f"/api/instances/{instance.id}/file",
            json={"path": "../evil.txt", "content": "x"},
            headers=headers(csrf),
        )
        assert bad.status == 400

        delete = await client.delete(
            f"/api/instances/{instance.id}/file?path=config/new.txt", headers=headers(csrf)
        )
        assert delete.status == 200
        assert not (root / "config" / "new.txt").exists()


# ---------- 导出 ----------



async def wait_job(client, job_id: str, timeout: float = 10.0) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        resp = await client.get(f"/api/jobs/{job_id}")
        data = await resp.json()
        if data.get("finished"):
            return data
        await asyncio.sleep(0.05)
    raise AssertionError("job 没有在超时内完成")


async def test_export_zip_contains_files(tmp_path):
    app, _, instance, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        started = await client.post(
            f"/api/instances/{instance.id}/export?include=world,config", headers=headers(csrf)
        )
        assert started.status == 200
        job = (await started.json())["job"]
        done = await wait_job(client, job["id"])
        assert done["error"] == ""
        resp = await client.get(f"/api/jobs/{job['id']}/download")
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "application/zip"
        blob = await resp.read()
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            names = archive.namelist()
        assert "world/level.dat" in names
        assert "server.properties" in names
        assert not any(name.startswith("logs/") for name in names)


# ---------- 导入 ----------


def make_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


async def test_import_zip_rejects_escape(tmp_path):
    app, _, instance, root = make_app(tmp_path)
    payload = make_zip({"ok.txt": b"fine", "../escape.txt": b"bad"})
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        form = FormData()
        form.add_field("file", payload, filename="up.zip", content_type="application/zip")
        resp = await client.post(
            f"/api/instances/{instance.id}/import", data=form, headers=headers(csrf)
        )
        assert resp.status == 200
        body = await resp.json()
        assert (root / "ok.txt").read_text() == "fine"
        assert body["skipped"], "越界条目应被跳过"
        assert not (tmp_path / "escape.txt").exists()


# ---------- 备份 ----------


async def test_backup_create_list_restore_delete(tmp_path):
    app, _, instance, root = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        created = await client.post(f"/api/instances/{instance.id}/backup", json={}, headers=headers(csrf))
        assert created.status == 200, await created.text()
        payload = await created.json()
        done = await wait_job(client, payload["job"]["id"])
        assert done["error"] == ""
        name = done["result"]["name"]

        listing = await client.get(f"/api/instances/{instance.id}/backups")
        assert [b["name"] for b in (await listing.json())["backups"]] == [name]

        (root / "world" / "level.dat").write_bytes(b"changed")
        restored = await client.post(
            f"/api/instances/{instance.id}/backups/{name}/restore", headers=headers(csrf)
        )
        assert restored.status == 200
        assert (root / "world" / "level.dat").read_bytes() == b"level"

        deleted = await client.delete(
            f"/api/instances/{instance.id}/backups/{name}", headers=headers(csrf)
        )
        assert deleted.status == 200
        listing = await client.get(f"/api/instances/{instance.id}/backups")
        assert (await listing.json())["backups"] == []


# ---------- 整合包导入 ----------


def pack_bytes() -> bytes:
    manifest = "Manifest-Version: 1.0\nMain-Class: net.minecraft.server.Main\n"
    core = make_zip({"META-INF/MANIFEST.MF": manifest.encode()})
    return make_zip(
        {
            "server.properties": b"level-name=world\n",
            "eula.txt": b"eula=true\n",
            "server.jar": core,
        }
    )


async def test_import_pack_creates_instance(tmp_path):
    app, config, instance, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        form = FormData()
        form.add_field("name", "新整合包")
        form.add_field("file", pack_bytes(), filename="pack.zip", content_type="application/zip")
        resp = await client.post("/api/packs/import", data=form, headers=headers(csrf))
        assert resp.status == 200, await resp.text()
        body = await resp.json()
        assert body["instance"]["name"] == "新整合包"
        assert (Path(config.get("app.servers_dir")) / "新整合包" / "server.jar").exists()

        again = FormData()
        again.add_field("name", "新整合包")
        again.add_field("file", pack_bytes(), filename="pack.zip", content_type="application/zip")
        dup = await client.post("/api/packs/import", data=again, headers=headers(csrf))
        assert dup.status == 409



async def test_export_cancel(tmp_path):
    app, _, instance, root = make_app(tmp_path)
    for index in range(200):
        (root / "world" / f"chunk-{index}.bin").write_bytes(b"x" * 4096)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        started = await client.post(
            f"/api/instances/{instance.id}/export?include=world", headers=headers(csrf)
        )
        job = (await started.json())["job"]
        cancel = await client.post(f"/api/jobs/{job['id']}/cancel", headers=headers(csrf))
        assert cancel.status == 200
        done = await wait_job(client, job["id"])
        assert done["cancelled"] is True or done["error"] == "已取消"
        download = await client.get(f"/api/jobs/{job['id']}/download")
        assert download.status == 404


async def test_import_options_gate_remote(tmp_path):
    app, config, instance, _ = make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        opts = await client.get("/api/packs/import-options")
        body = await opts.json()
        assert body["adopt"]["enabled"] is True
        assert body["remote"]["enabled"] is False
        assert "未允许服务器从网址下载" in body["remote"]["reason"]
        assert body["zip"]["hint"] and body["adopt"]["hint"] and body["path"]["hint"]

        blocked = await client.post(
            "/api/packs/import-url",
            json={"url": "https://example.com/pack.zip", "name": "x"},
            headers=headers(csrf),
        )
        assert blocked.status == 403

        config.set("files.allow_remote_download", True)
        resp2 = await client.get("/api/packs/import-options")
        opts2 = await resp2.json()
        assert opts2["remote"]["enabled"] is True


async def test_adopt_existing_directory(tmp_path):
    app, _, instance, root = make_app(tmp_path)
    extra = tmp_path / "another-server"
    (extra / "world").mkdir(parents=True)
    (extra / "server.jar").write_bytes(b"")
    manifest = "Manifest-Version: 1.0\nMain-Class: net.minecraft.server.Main\n"
    (extra / "server.jar").write_bytes(make_zip({"META-INF/MANIFEST.MF": manifest.encode()}))
    (extra / "eula.txt").write_text("eula=true", encoding="utf-8")
    (extra / "server.properties").write_text("level-name=world", encoding="utf-8")
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        resp = await client.post(
            "/api/packs/adopt",
            json={"directory": str(extra), "name": "接管测试"},
            headers=headers(csrf),
        )
        assert resp.status == 200, await resp.text()
        body = await resp.json()
        assert body["instance"]["name"] == "接管测试"
        assert body["instance"]["launch_mode"] == "jar"


async def test_import_zip_on_server_disk(tmp_path):
    app, config, instance, _ = make_app(tmp_path)
    servers = Path(config.get("app.servers_dir"))
    source = tmp_path / "local-pack.zip"
    source.write_bytes(pack_bytes())
    async with TestClient(TestServer(app)) as client:
        csrf = await login(client)
        resp = await client.post(
            "/api/packs/import-path",
            json={"path": str(source), "name": "磁盘导入"},
            headers=headers(csrf),
        )
        assert resp.status == 200, await resp.text()
        body = await resp.json()
        assert body["instance"]["name"] == "磁盘导入"
        assert (servers / "磁盘导入" / "server.jar").exists()

        again = await client.post(
            "/api/packs/import-path",
            json={"path": str(source), "name": "磁盘导入"},
            headers=headers(csrf),
        )
        assert again.status == 409

        missing = await client.post(
            "/api/packs/import-path",
            json={"path": str(tmp_path / "nope.zip"), "name": "x"},
            headers=headers(csrf),
        )
        assert missing.status == 400
