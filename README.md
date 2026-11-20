# 星岚 / HoshiLauncher

把 MCSL2 这类开服工具从桌面程序改写成「常驻服务 + 浏览器控制台」的个人向面板。单人使用，资源占用尽量小，能跑在 4 核 16 GB 的租用机上。

## 引用与鸣谢 / Credits

| 对象 | 作用 | 说明 |
|---|---|---|
| [MCSL2](https://github.com/MCSLTeam/MCSL2) | 上游基线 | © MCSL开发组，GPL-3.0。本仓库保留其许可与出处 |
| [BlueMap](https://github.com/BlueMap-Minecraft/BlueMap) | 网页地图渲染 | MIT，bluecolored |
| [CreateTrainWebAPI](https://github.com/BeneHenke/CreateTrainWebAPI) | Create 列车与轨道数据 | MIT，BeneHenke |
| [Create BlueMap](https://github.com/Szedann/create-bluemap) | 备选列车渲染 | MIT，Szedann |
| [AstrBot](https://github.com/AstrBotDevs/AstrBot) | QQ bot 插件宿主 | AGPL-3.0 |
| [Create](https://github.com/Creators-of-Create/Create) | 列车数据来源 | MIT |
| mc-download-guide | 下载链路实测与方法 | 本地文档，作者未公开托管 |
| Python、aiohttp | 运行时与 HTTP | PSF、Apache-2.0 |
| [Modrinth API](https://docs.modrinth.com) | 模组元数据与侧别判定 | 服务条款 |
| [BMCLAPI](https://bmclapi2.bangbang93.com) | Minecraft 资源镜像 | bangbang93 维护 |

## AI 生成警告 / AI Notice

> **本仓库的文档与代码主要由 AI 协助生成与整理。**
>
> - 可能存在事实错误、版本漂移、参数记错，尤其涉及具体行号、命令输出、第三方接口字段的部分。
> - 项目仍在开发中，接口、配置项、目录结构随时会变。
> - 不要把这里的内容当成权威结论；动手前请对照上游源码、官方文档与你自己的实测。
> - 任何涉及公网暴露、删除数据、改服务器配置的操作，先在测试环境验证。

English: **Documents and code here are largely AI-generated.** Expect factual errors, version drift and outdated API details. Verify against upstream sources before relying on anything, and never run destructive steps without a backup.

## 现在是什么状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| R0 | 配置 schema、TOML 读写、CLI、SQLite、健康检查 | 已完成 |
| R1 | 实例模型、Java 探测、进程守护、WebSocket 控制台、登录 | 已完成 |
| R2 | 设置页、公网三档、TOTP 与二维码、限速、审计页、改密码、命令白名单 | 已完成 |
| R3 | 参数编辑、导入、下载、模组管理、目录迁移、bot 接口 | 未开始 |
| R4 | 地图、玩家层、标记、分享链接 | 未开始 |
| R5 | 打包、自启、旧数据迁移、发布 | 未开始 |

R1、R2 已完成：62 项测试通过，空载 USS 24 MB、RSS 44 MB；香草纪元服务端实测从点击到 `Done` 用 125 秒。

## 目录结构

```
.
├── README.md              本文件（中英对照）
├── LICENSE                GPL-3.0 正文
├── NOTICE.md              上游、第三方组件与改动记录
├── pyproject.toml         Python 工程
├── src/hoshi/             服务端程序包（src 布局）
│   ├── config/            配置 schema、加载、TOML 写出
│   ├── web/               aiohttp 应用与路由
│   ├── cli.py             命令行入口
│   └── db.py              SQLite 初始化与审计
├── tests/                 单元测试
├── docs/使用指南.md        给使用者的教程，仓库里唯一的文档
├── evidence/              上游源码副本，本地保留，不入库
└── archive/mcsl2-fork/    PyQt 版骨架，历史归档，不入库
```

上游解剖、选型与实施记录都是本地笔记，不随仓库分发。`evidence/`、`archive/`、`notes/` 都写入 `.gitignore`。

## 快速开始

```powershell
# 需要 Python 3.12
uv venv --python 3.12
uv pip install -e ".[dev]"

# 生成默认配置、校验、启动
uv run python -m hoshi --init-config
uv run python -m hoshi --check-config
uv run python -m hoshi            # 默认 127.0.0.1:25566

# 测试与静态检查
uv run pytest -q
uv run ruff check .
```

国内网络装依赖可能卡住，可加 `--index-url https://pypi.tuna.tsinghua.edu.cn/simple`。

## 文档

只有一份：[使用指南](docs/使用指南.md)。装好、登录、接管已有服务端目录、启停看日志，都在里面。

## 许可与分发

GPL-3.0。分发二进制时请一并提供源码与 `NOTICE.md`。第三方组件的许可见 `NOTICE.md`，地图组件不随仓库分发。

---

# HoshiLauncher (English)

A personal Minecraft server panel that turns a desktop launcher into a long-running service with a browser UI. Single operator, small footprint, intended for a 4-core / 16 GB rented box.

## Credits

See the table above. Upstream MCSL2 is © MCSL开发组 under GPL-3.0; BlueMap and CreateTrainWebAPI are MIT; AstrBot is AGPL-3.0.

## AI Notice

**Documents and code in this repo are largely AI-generated.** Expect factual errors, version drift and outdated API details. Verify against upstream sources, and back up before any destructive step.

## Status

R1 and R2 are done: 62 tests pass, idle RSS 44 MB / USS 24 MB, and a 400-mod Forge pack booted to `Done` in 125 s. R2 to R5 are not started.

## Layout

`hoshi/` holds the Python package, `tests/` the unit tests, `docs/` a single user guide. Design notes, probes, `evidence/` and `archive/` stay local and gitignored.

## Quick start

```powershell
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run python -m hoshi --init-config
uv run python -m hoshi
```

## License

GPL-3.0. Ship the source and `NOTICE.md` together with any binary you distribute. Map components are fetched at runtime, not bundled.




