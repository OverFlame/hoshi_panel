"""配置项定义。

一份 schema 同时驱动三样东西：设置页的渲染、值的校验、文档与 `/api/settings` 的输出。
每个字段都带「是什么、为什么、何时生效、风险多大」，避免三个月后看不懂。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Kind = Literal["bool", "int", "enum", "str", "path", "list"]


@dataclass(frozen=True)
class Item:
    key: str
    kind: Kind
    default: Any
    label: str
    summary: str
    why: str
    group: str
    restart: bool = False
    risk: Literal["low", "medium", "high"] = "low"
    values: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    secret: bool = False
    requires: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def coerce(self, raw: Any) -> Any:
        """把外部输入转成该字段的类型，转不了就抛 ValueError。"""
        if self.kind == "bool":
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, str) and raw.lower() in ("true", "false"):
                return raw.lower() == "true"
            raise ValueError(f"{self.key}: 需要布尔值")
        if self.kind == "int":
            try:
                return int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{self.key}: 需要整数") from exc
        if self.kind == "enum":
            text = str(raw)
            if text not in self.values:
                raise ValueError(f"{self.key}: 只能是 {', '.join(self.values)}")
            return text
        if self.kind == "list":
            if isinstance(raw, list):
                return [str(x) for x in raw]
            if isinstance(raw, str):
                return [x.strip() for x in raw.split(",") if x.strip()]
            raise ValueError(f"{self.key}: 需要列表")
        return str(raw)

    def validate(self, value: Any) -> None:
        if self.kind == "int":
            if self.minimum is not None and value < self.minimum:
                raise ValueError(f"{self.key}: 不能小于 {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise ValueError(f"{self.key}: 不能大于 {self.maximum}")
        if self.kind == "path" and not str(value).strip():
            raise ValueError(f"{self.key}: 路径不能为空")


SCHEMA: tuple[Item, ...] = (
    # ---------------- 应用 ----------------
    Item(
        key="app.data_dir",
        kind="path",
        default="./data",
        label="数据目录",
        summary="配置、数据库、日志、缓存的存放位置",
        why="想把这些文件放到数据盘时改这里。只在启动时读取，改完要重启。",
        group="应用",
        restart=True,
        risk="medium",
    ),
    Item(
        key="app.servers_dir",
        kind="path",
        default="./Servers",
        label="服务器存放目录",
        summary="所有实例的父目录",
        why="实例占空间大，通常放到单独的数据盘。改这里不影响已有实例，要搬请用迁移功能。",
        group="应用",
        restart=True,
        risk="medium",
    ),
    Item(
        key="app.log_level",
        kind="enum",
        default="info",
        values=("debug", "info", "warning", "error"),
        label="日志级别",
        summary="面板自身日志的详细程度",
        why="排查问题时临时调成 debug，平时用 info，避免日志膨胀。",
        group="应用",
    ),
    # ---------------- 网络 ----------------
    Item(
        key="web.bind",
        kind="str",
        default="127.0.0.1",
        label="监听地址",
        summary="面板绑定的网卡地址",
        why="默认只给本机访问。改成 0.0.0.0 等于对外开放，请配合公网暴露开关与 TOTP。",
        group="网络与访问",
        restart=True,
        risk="high",
    ),
    Item(
        key="web.port",
        kind="int",
        default=25566,
        minimum=1,
        maximum=65535,
        label="监听端口",
        summary="浏览器访问面板用的端口",
        why="默认 25566，避免与服务端默认的 25565 冲突。被占用时启动会直接报错。",
        group="网络与访问",
        restart=True,
    ),
    Item(
        key="web.theme",
        kind="enum",
        default="dark",
        values=("dark", "light"),
        label="界面主题",
        summary="深色或浅色，Tabler 内置",
        why="需要更细的调整时，把自定义 CSS 放到 data/theme.css，会自动加载。",
        group="网络与访问",
    ),
    Item(
        key="web.exposure",
        kind="enum",
        default="local",
        values=("local", "lan", "public"),
        label="公网暴露",
        summary="允许非本机设备访问面板",
        why="只在需要手机或外网访问时开。开启后登录页对网络可见，且必须启用 TOTP。",
        group="网络与访问",
        restart=True,
        risk="high",
        requires=(("auth.password_hash", "not_empty"),),
    ),
    Item(
        key="web.exposure_ack",
        kind="str",
        default="",
        label="对外开放确认短语",
        summary="改暴露档时必须手填这句话",
        why="防止误点。短语是「我确认对外开放」，与暴露档一起写进配置，启动时校验。",
        group="网络与访问",
        restart=True,
        risk="high",
    ),
    Item(
        key="web.behind_proxy",
        kind="bool",
        default=False,
        label="位于反向代理之后",
        summary="信任代理转发的地址信息",
        why="只有确实放在 Caddy 或 Nginx 后面才开，否则来源 IP 与限速会失真。",
        group="网络与访问",
        restart=True,
        risk="medium",
    ),
    # ---------------- 认证 ----------------
    Item(
        key="auth.username",
        kind="str",
        default="admin",
        label="管理员账号",
        summary="唯一可登录的账号名",
        why="单人使用，不做多用户。改名对已登录会话无影响。",
        group="认证",
    ),
    Item(
        key="auth.password_hash",
        kind="str",
        default="",
        label="密码散列",
        summary="argon2id 散列，不存明文",
        why="首次启动自动生成随机密码并写入 data/initial-password.txt，登录后强制修改。",
        group="认证",
        secret=True,
        risk="high",
    ),
    Item(
        key="auth.totp_enabled",
        kind="bool",
        default=False,
        label="两步验证",
        summary="登录时额外要 6 位动态码",
        why="公网暴露时强烈建议开启。恢复码共 10 个，只显示一次。",
        group="认证",
        risk="high",
    ),
    Item(
        key="auth.totp_secret",
        kind="str",
        default="",
        label="两步验证密钥",
        summary="base32 密钥，开启后登录要 6 位动态码",
        why="由设置页生成，不要手改。丢失时用恢复码或本地重置。",
        group="认证",
        secret=True,
        risk="high",
    ),
    Item(
        key="auth.totp_last_step",
        kind="int",
        default=0,
        label="两步验证最后步长",
        summary="防重放用，记录最近一次通过的时间步",
        why="同一个动态码只能用一次。",
        group="认证",
        secret=True,
    ),
    Item(
        key="auth.recovery_hashes",
        kind="list",
        default=[],
        label="恢复码散列",
        summary="一次性恢复码，存散列不存明文",
        why="手机丢了还能登录。用掉一个就少一个，界面只在生成时显示一次。",
        group="认证",
        secret=True,
        risk="high",
    ),
    Item(
        key="auth.session_idle_minutes",
        kind="int",
        default=30,
        minimum=5,
        maximum=1440,
        label="会话空闲超时",
        summary="多久不操作需要重新登录",
        why="面板能起停进程，超时太短影响体验，太长增加风险。",
        group="认证",
    ),
    Item(
        key="auth.session_absolute_hours",
        kind="int",
        default=12,
        minimum=1,
        maximum=720,
        label="会话最长时长",
        summary="无论是否活跃，到点重新登录",
        why="防止一次登录长期有效。",
        group="认证",
    ),
    # ---------------- 控制台 ----------------
    Item(
        key="security.login_fail_limit",
        kind="int",
        default=5,
        minimum=1,
        maximum=20,
        label="登录失败上限",
        summary="连续失败多少次触发锁定",
        why="按来源 IP 与账号分别计数。公网档建议 3 到 5 次。",
        group="安全",
        risk="medium",
    ),
    Item(
        key="security.login_lock_minutes",
        kind="int",
        default=15,
        minimum=1,
        maximum=1440,
        label="锁定时长",
        summary="触发上限后多久内禁止再试",
        why="锁太久自己也会被挡在外面，锁太短挡不住撞库。",
        group="安全",
        risk="medium",
    ),
    Item(
        key="console.command_mode",
        kind="enum",
        default="strict",
        values=("strict", "extended", "raw"),
        label="控制台命令模式",
        summary="是否限制只能发已知命令",
        why="strict 只放行原版与已发现的模组命令；raw 直送 stdin，仅建议在本机模式使用。",
        group="控制台与命令",
        risk="medium",
    ),
    Item(
        key="console.extra_commands",
        kind="list",
        default=[],
        label="额外允许的命令",
        summary="extended 模式下追加的命令名",
        why="模组命令抓不全是常态，把常用的补在这里。",
        group="控制台与命令",
    ),
    # ---------------- Java ----------------
    Item(
        key="java.allow_custom_jvm_args",
        kind="bool",
        default=True,
        label="允许自定义 JVM 参数",
        summary="是否接受用户填写的附加参数",
        why="关掉后只能用面板生成的内存参数。危险参数始终会被拦截，与这一项无关。",
        group="Java",
        risk="medium",
    ),
    # ---------------- 地图 ----------------
    Item(
        key="map.enabled",
        kind="bool",
        default=False,
        label="网页地图",
        summary="启用 BlueMap 底图",
        why="默认关闭。开启会占用一个渲染线程与额外磁盘，4 核机器上尤其明显。",
        group="地图",
        restart=True,
        risk="medium",
    ),
    Item(
        key="map.render_threads",
        kind="int",
        default=1,
        minimum=0,
        maximum=4,
        label="渲染线程数",
        summary="BlueMap 占用的线程",
        why="4 核机器保持 1，把其余核心留给服务端 tick。",
        group="地图",
        restart=True,
    ),
    Item(
        key="map.download_mirror",
        kind="str",
        default="",
        label="BlueMap 下载镜像",
        summary="留空走 Modrinth，填完整 URL 则直接下载这个地址",
        why="国内访问 GitHub 或 Modrinth 慢时用，URL 要指向一个 jar 文件。",
        group="地图",
    ),
    Item(
        key="map.upstream",
        kind="str",
        default="http://127.0.0.1:8100",
        label="BlueMap 上游地址",
        summary="面板把 /map/ 反代到这个地址",
        why="BlueMap 默认 8100。放在同一台机器时保持默认。",
        group="地图",
    ),
    Item(
        key="map.accept_download",
        kind="bool",
        default=False,
        label="同意 BlueMap 下载资源",
        summary="BlueMap 需要下载客户端资源才能渲染",
        why="这是 BlueMap 的硬性要求。开启前请确认你接受它的条款。",
        group="地图",
        risk="medium",
    ),
    Item(
        key="map.player_poll_seconds",
        kind="int",
        default=5,
        minimum=1,
        maximum=60,
        label="玩家位置轮询间隔",
        summary="通过 RCON 拉坐标的频率",
        why="越频繁越实时，但会给服端增加 RCON 请求。",
        group="地图",
    ),
    Item(
        key="map.share_ttl_hours",
        kind="int",
        default=24,
        minimum=1,
        maximum=720,
        label="共享链接有效期",
        summary="只读地图链接能用多久",
        why="过期后链接自动失效，不用手动撤销。",
        group="地图",
    ),
    Item(
        key="map.hires_distance",
        kind="int",
        default=0,
        minimum=0,
        maximum=500,
        label="高清渲染距离",
        summary="0 表示只渲染低清",
        why="高清瓦片是内存与磁盘的主要开销，个人服通常不需要。",
        group="地图",
        restart=True,
    ),
    # ---------------- bot ----------------
    Item(
        key="bot.group_limit",
        kind="int",
        default=10,
        minimum=1,
        maximum=120,
        label="bot 每群每分钟查询次数",
        summary="按令牌绑定群限速",
        why="防止群里刷屏。默认 10 次，够用且不会把服端日志刷乱。",
        group="bot",
        risk="low",
    ),
    Item(
        key="bot.user_limit",
        kind="int",
        default=1,
        minimum=1,
        maximum=60,
        label="bot 每人每分钟查询次数",
        summary="按 X-Bot-User 头限速",
        why="插件侧也应做一层，这里兜底。",
        group="bot",
        risk="low",
    ),
    Item(
        key="bot.limit_message",
        kind="str",
        default="查询太频繁，{wait} 秒后再试",
        label="超限提示",
        summary="bot 查询被限速时的话术",
        why="支持占位符 {wait}。改这里不用动插件。",
        group="bot",
    ),
    Item(
        key="bot.status_template",
        kind="str",
        default="",
        label="状态文案模板",
        summary="留空用内置模板，占位符见文档",
        why="想改措辞不用改代码。支持 {instance} {state} {online} {names} {tps} {uptime} {last_event}。",
        group="bot",
    ),
    # ---------------- 文件 ----------------
    Item(
        key="files.allow_remote_download",
        kind="bool",
        default=False,
        label="允许服务器从网址下载 zip",
        summary="导入整合包时，让服务器替你下载一个 http(s) 地址",
        why="关掉时导入只能用服务器上的文件或从浏览器上传。"
        "开启后服务器会主动访问你填的地址，等于把出站请求交给你，公网暴露与否无关，"
        "请只在下你能信任该地址时使用。",
        group="文件与备份",
        risk="medium",
    ),
    Item(
        key="files.max_upload_mb",
        kind="int",
        default=4096,
        minimum=1,
        maximum=65536,
        label="上传大小上限",
        summary="导入 zip 与整合包的单个文件上限",
        why="超过就走 SFTP。默认 4 GB。",
        group="文件与备份",
        risk="medium",
    ),
    # ---------------- 模组 ----------------
    Item(
        key="mods.side_lookup",
        kind="bool",
        default=True,
        label="在线查询模组侧别",
        summary="用 Modrinth 判断模组属于客户端还是服务端",
        why="关掉后只能用本地元数据与内置清单，未知项会变多。",
        group="模组",
    ),
)

BY_KEY: dict[str, Item] = {item.key: item for item in SCHEMA}


def groups() -> dict[str, list[Item]]:
    out: dict[str, list[Item]] = {}
    for item in SCHEMA:
        out.setdefault(item.group, []).append(item)
    return out
