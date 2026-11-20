import json
from pathlib import Path

from hoshi.auth import hash_password, verify_password
from hoshi.auth.sessions import SessionStore
from hoshi.instances import Instance, InstanceRegistry, detect

FAKE_JAVA = str(Path(__file__).with_name("fake_java.py"))


def make_server_dir(tmp_path: Path) -> Path:
    root = tmp_path / "server"
    (root / "libraries" / "net" / "minecraftforge" / "forge" / "1.20.1-47.3.33").mkdir(parents=True)
    (root / "libraries" / "net" / "minecraftforge" / "forge" / "1.20.1-47.3.33" / "win_args.txt").write_text(
        "-p libraries/cpw/mods/bootstraplauncher.jar\n", encoding="utf-8"
    )
    (root / "win_args.txt").write_text("-p libraries/x\n", encoding="utf-8")
    (root / "user_jvm_args.txt").write_text("# args\n", encoding="utf-8")
    (root / "server.properties").write_text(
        "level-name=world\nserver-port=25565\nmotd=香草纪元\n", encoding="utf-8"
    )
    (root / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    return root


# ---------- 目录识别 ----------


def test_detect_args_file_layout(tmp_path):
    root = make_server_dir(tmp_path)
    result = detect(root)
    assert result.ok
    assert result.launch_mode == "args_file"
    assert result.args_file.endswith("win_args.txt")
    assert "minecraftforge" in result.args_file
    assert result.loader == "forge"
    assert result.loader_version == "1.20.1-47.3.33"
    assert result.mc_version == "1.20.1"
    assert result.user_jvm_args == "user_jvm_args.txt"
    assert result.eula_accepted is True
    assert result.server_properties["motd"] == "香草纪元"


def test_detect_empty_dir(tmp_path):
    result = detect(tmp_path / "empty")
    assert not result.ok
    assert result.warnings


def test_detect_jar_layout(tmp_path):
    import zipfile

    root = tmp_path / "jar-server"
    root.mkdir()
    (root / "server.properties").write_text("level-name=world\n", encoding="utf-8")
    with zipfile.ZipFile(root / "server.jar", "w") as z:
        z.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nMain-Class: net.minecraft.server.Main\n")
    result = detect(root)
    assert result.ok
    assert result.launch_mode == "jar"
    assert result.jar == "server.jar"


# ---------- 实例与参数 ----------


def test_instance_argv_args_file(tmp_path):
    instance = Instance.new(
        name="香草",
        directory=str(tmp_path),
        launch_mode="args_file",
        args_file="libraries/net/minecraftforge/forge/1.20.1-47.3.33/win_args.txt",
        user_jvm_args="user_jvm_args.txt",
        java="java",
        min_memory_mb=2048,
        max_memory_mb=8192,
    )
    argv = instance.argv()
    assert argv[0] == "-Xms2048M"
    assert argv[1] == "-Xmx8192M"
    assert argv[2] == "@user_jvm_args.txt"
    assert argv[3].endswith("win_args.txt")
    assert argv[-1] == "nogui"


def test_instance_argv_jar(tmp_path):
    instance = Instance.new(
        name="vanilla",
        directory=str(tmp_path),
        launch_mode="jar",
        jar="server.jar",
        java="java",
        jvm_args=["-XX:+UseG1GC"],
    )
    argv = instance.argv()
    assert "-jar" in argv
    assert argv[argv.index("-jar") + 1] == "server.jar"
    assert "-XX:+UseG1GC" in argv


def test_registry_roundtrip(tmp_path):
    path = tmp_path / "instances.json"
    registry = InstanceRegistry(path)
    instance = Instance.new(
        name="test", directory=str(tmp_path / "srv"), java=FAKE_JAVA, launch_mode="jar", jar="x.jar"
    )
    registry.add(instance)
    assert json.loads(path.read_text(encoding="utf-8"))["instances"][0]["name"] == "test"

    again = InstanceRegistry(path)
    assert again.get(instance.id).name == "test"
    assert again.get("test").id == instance.id


# ---------- 认证 ----------


def test_password_hash_and_verify():
    stored = hash_password("correct horse battery staple")
    assert stored.startswith("scrypt$")
    assert verify_password("correct horse battery staple", stored)
    assert not verify_password("wrong", stored)


def test_session_lifecycle(monkeypatch):
    store = SessionStore(idle_minutes=1, absolute_hours=1)
    session = store.create("admin")
    assert store.get(session.token) is not None
    session.last_seen -= 120  # 模拟闲置超时
    assert store.get(session.token) is None
    assert len(store) == 0


def test_session_absolute_limit():
    store = SessionStore(idle_minutes=60, absolute_hours=1)
    session = store.create("admin")
    session.created -= 3700
    session.last_seen -= 1
    assert store.get(session.token) is None

def test_decode_line_handles_mixed_encodings():
    from hoshi.instances.supervisor import decode_line

    assert decode_line("香草".encode()) == "香草"
    assert decode_line("新".encode("gb18030")) == "新"
    assert decode_line("路径 D:\\\\MC\\\\香草".encode("gb18030")) == "路径 D:\\\\MC\\\\香草"
    assert "\ufffd" in decode_line(b"\xff\xfe\x00bad")


def test_java_range_and_pick():
    from hoshi.instances.java import JavaInfo, pick_for, required_majors

    assert required_majors("1.20.1") == (17, 21)
    assert required_majors("1.21.4") == (21, 25)
    assert required_majors("1.16.5") == (8, 16)

    candidates = [
        JavaInfo(path="jdk25", version="25"),
        JavaInfo(path="jdk21", version="21.0.9"),
        JavaInfo(path="jdk17", version="17.0.16"),
        JavaInfo(path="jdk8", version="1.8.0_51"),
    ]
    assert pick_for("1.20.1", candidates).path == "jdk21"
    assert pick_for("1.16.5", candidates).path == "jdk8"
    assert pick_for("1.21.4", candidates).path == "jdk25"
    assert pick_for("1.20.1", [JavaInfo(path="jdk25", version="25")]) is None

def test_quiet_disconnect_filter():
    import asyncio

    from hoshi.compat import install_quiet_disconnects

    loop = asyncio.new_event_loop()
    seen: list[str] = []
    loop.set_exception_handler(lambda _loop, ctx: seen.append(str(ctx.get("message"))))
    install_quiet_disconnects(loop)

    handler = loop.get_exception_handler()
    assert handler is not None
    handler(loop, {"message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
                   "exception": ConnectionResetError(10054, "远程主机强迫关闭了一个现有的连接")})
    assert seen == [], "断连不应进入默认处理器"

    handler(loop, {"message": "其他错误", "exception": ValueError("boom")})
    assert seen == ["其他错误"], "其他异常要照常上报"
    loop.close()
