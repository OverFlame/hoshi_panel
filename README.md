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
| [Modrinth API](https://docs.modrinth.com) | 模组元数据与侧别判定 | 服务条款 |
| [BMCLAPI](https://bmclapi2.bangbang93.com) | Minecraft 资源镜像 | bangbang93 维护 |
| [psutil](https://github.com/giampaolo/psutil) | 进程与主机指标 | BSD-3-Clause |
| [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) | 界面等宽字体 | SIL OFL 1.1，全文见 `LICENSES/` |
| [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts) | 字体图标补丁 | 字体 OFL 1.1，脚本 MIT |
| Python、aiohttp、segno | 运行时、HTTP、二维码 | PSF、Apache-2.0、BSD |

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
| R3 | 文件、备份、导出导入、整合包导入、模组、属性编辑、迁移、bot、诊断 | 已完成 |
| R4 | 地图、玩家层、标记、分享链接 | 已完成 |
| R5 | 打包、系统服务、旧数据迁移、发布包 | 已完成 |

实测数据：

| 指标 | 值 |
|---|---|
| 测试 | 110 项通过，ruff 无告警 |
| 面板空载 | RSS 44 MB，USS 24 MB，9 线程 |
| 打包产物 | `hoshi.exe` 19.0 MB，整个目录 39.8 MB |
| 发布包 | `hoshi-0.1.0-windows-x64.zip` 14.6 MB |
| 香草纪元（400 模组 Forge） | 本机 125 秒；你的安装用 Java 17 实测 207 秒 |

## 能做什么

| 范围 | 能力 |
|---|---|
| 实例 | 接管已有目录、导入 zip 整合包并自动识别、迁移目录、每个实例单独设 Java 与内存 |
| 进程 | 启动、停止、强杀，独立进程组，日志环形缓冲 2000 行并落盘 |
| 控制台 | 实时 WebSocket、命令白名单三档（strict / extended / raw） |
| 文件 | 目录浏览、文本在线编辑、`server.properties` 保序编辑（保留注释、自动 `.bak`） |
| 备份 | 创建、列举、恢复、删除，默认保留 10 份，运行中拒绝恢复 |
| 导入导出 | 流式导出 zip（store 不压缩）、安全解包导入、带进度条 |
| 模组 | 列表、侧别判定（fabric / mods.toml / 内置名单 / Modrinth 反查）、一键启停 |
| 安全 | 登录、TOTP（扫码 / 终端出码 / 恢复码）、登录限速锁定、审计页、CSRF、JVM 参数白名单、暴露三档 |
| 地图 | BlueMap 配置生成（复用现有世界）、`/map/` 反代、RCON 玩家位置、标记写入地图配置、只读共享链接、玩家浮层 |
| bot | 只读令牌、状态 / 玩家 / 事件接口、每群 10 次与每人 1 次限速、文案可配 |
| 运维 | 崩溃诊断（九类模式）、快捷命令、审计与设置改动历史、旧 MCSL2 数据迁移 |

## 目录结构

```
.
├── README.md              本文件（中英对照）
├── QUICKSTART.md          三分钟上手
├── LICENSE                GPL-3.0 正文
├── NOTICE.md              上游、第三方组件与改动记录
├── LICENSES/              第三方许可全文（字体等）
├── pyproject.toml         Python 工程
├── src/hoshi/             服务端程序包（src 布局）
│   ├── auth/              密码、TOTP、恢复码、限速、会话
│   ├── instances/         实例、探测、进程、备份、迁移、诊断、属性
│   ├── files/             路径安全与 zip
│   ├── map/               BlueMap、RCON、玩家、标记、共享
│   ├── mods/              jar 元数据与 Modrinth
│   ├── bot/               只读接口与限速
│   ├── security/          命令与 JVM 白名单、暴露档
│   ├── web/               aiohttp 应用与页面
│   ├── cli.py             命令行入口
│   └── db.py              SQLite 与审计
├── tests/                 单元与接口测试（110 项）
├── packaging/             Nuitka 构建、systemd 单元、NSSM 脚本、发布打包
├── docs/使用指南.md        给使用者的教程，仓库里唯一的文档
├── evidence/              上游源码副本，本地保留，不入库
├── notes/                 设计与决策笔记，本地保留，不入库
└── archive/mcsl2-fork/    PyQt 版骨架，历史归档，不入库
```

`evidence/`、`notes/`、`archive/`、`dist/`、`release/` 都在 `.gitignore` 里。

## 快速开始

用发布包（不需要 Python）：

```powershell
.\hoshi.exe serve
```

从源码：

```powershell
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run python -m hoshi --init-config
uv run python -m hoshi            # 默认 127.0.0.1:25566
uv run pytest -q
uv run ruff check .
```

国内网络装依赖慢，可加 `--index-url https://pypi.tuna.tsinghua.edu.cn/simple`。

## 文档

| 文件 | 内容 |
|---|---|
| [QUICKSTART.md](QUICKSTART.md) | 三分钟跑起来 |
| [docs/使用指南.md](docs/使用指南.md) | 完整使用手册：实例、控制台、文件、备份、模组、地图、bot、安全 |
| [packaging/README.md](packaging/README.md) | 打包、systemd、NSSM、发布包、旧数据迁移 |

## 已知边界

| 项 | 现状 |
|---|---|
| 地图组件 | 不随仓库分发，需自备 BlueMap jar |
| Create 列车实体 | 需要 CreateTrainWebAPI，暂未接入 |
| 下载层 | 未实现「从零下载并安装整合包」，只支持接管已有目录与 zip 导入 |
| 定时任务 | 未实现 |
| 按实例的地图与模组设置 | 目前这些仍是全局配置，已列入下一批改造 |

## 许可与分发

GPL-3.0。分发二进制时请一并提供源码与 `NOTICE.md`。字体按 SIL OFL 1.1 分发，全文见 `LICENSES/OFL-1.1-JetBrainsMono.txt`。地图组件与 Minecraft 资源不在仓库内。

---

# HoshiLauncher (English)

A personal Minecraft server panel: one long-running service plus a browser UI. Single operator, small footprint, meant for a 4-core / 16 GB rented box.

## Credits

Upstream MCSL2 is © MCSL开发组 under GPL-3.0. BlueMap and CreateTrainWebAPI are MIT, AstrBot is AGPL-3.0, psutil is BSD-3-Clause, JetBrains Mono and the Nerd Fonts patch are SIL OFL 1.1. See the table above and `LICENSES/`.

## AI Notice

**Documents and code in this repo are largely AI-generated.** Expect factual errors, version drift and outdated API details. Verify against upstream sources, and back up before any destructive step.

## Status

Phases R0 to R5 are complete: 110 tests pass, idle RSS 44 MB / USS 24 MB, the packaged build is a 39.8 MB directory, and a 400-mod Forge pack reaches `Done` in about two to three minutes.

## Features

Instance adoption and zip import, process supervision, live console with a command allowlist, file browser and `server.properties` editor, backups, streaming zip export, mod side detection via Modrinth, TOTP with QR and terminal codes, audit log, BlueMap configuration and reverse proxy, map markers, read-only share links, and a token-limited bot API.

## Layout

`src/hoshi/` holds the package, `tests/` the suite, `docs/` a single user guide, `packaging/` the Nuitka build and service files. `evidence/`, `notes/` and `archive/` stay local and gitignored.

## Quick start

```powershell
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run python -m hoshi
```

Or use the release build: `hoshi.exe serve`.

## License

GPL-3.0. Ship the source and `NOTICE.md` with any binary. Fonts are SIL OFL 1.1, full text in `LICENSES/`. Map components and Minecraft assets are not bundled.
