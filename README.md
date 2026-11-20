# 星岚 / HoshiLauncher

在浏览器里管你的 Minecraft 服务器：启动、看日志、发命令、备份、装模组、看地图。一个程序，一个人用，常驻后台。

不需要开着启动器窗口，也不用记一堆脚本参数。

## 引用与鸣谢 / Credits

| 对象 | 作用 | 说明 |
|---|---|---|
| [MCSL2](https://github.com/MCSLTeam/MCSL2) | 项目起点 | © MCSL开发组，GPL-3.0 |
| [BlueMap](https://github.com/BlueMap-Minecraft/BlueMap) | 网页地图 | MIT，bluecolored |
| [CreateTrainWebAPI](https://github.com/BeneHenke/CreateTrainWebAPI) | Create 列车数据 | MIT，BeneHenke |
| [Create BlueMap](https://github.com/Szedann/create-bluemap) | 备选列车渲染 | MIT，Szedann |
| [AstrBot](https://github.com/AstrBotDevs/AstrBot) | QQ 机器人框架 | AGPL-3.0 |
| [Create](https://github.com/Creators-of-Create/Create) | 列车数据来源 | MIT |
| [Modrinth](https://docs.modrinth.com) | 模组信息查询 | 服务条款 |
| [BMCLAPI](https://bmclapi2.bangbang93.com) | Minecraft 资源镜像 | bangbang93 维护 |
| [psutil](https://github.com/giampaolo/psutil) | 内存与 CPU 读取 | BSD-3-Clause |
| [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) | 界面字体 | SIL OFL 1.1，全文见 `LICENSES/` |
| [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts) | 字体图标补丁 | 字体 OFL 1.1，脚本 MIT |
| [Tabler](https://github.com/tabler/tabler) | 界面主题 | MIT |
| Python、aiohttp、segno | 运行时、网页服务、二维码 | PSF、Apache-2.0、BSD |

## AI 生成警告 / AI Notice

> **这个项目的文档和代码主要由 AI 协助写成。**
>
> - 可能有事实错误、版本对不上、参数记错。
> - 功能还在增加，界面和配置项会变。
> - 动手前请对照官方文档和你自己的实际情况，重要操作先备份。

English: **Documents and code here are largely AI-generated.** Expect factual errors and outdated details. Verify before relying on anything, and back up before destructive steps.

## 你能用它做什么

### 概览与详情

- 打开就是概览：服务器数、在线玩家、整机内存与 CPU，一屏看完。
- 每台服务器一张卡片，显示状态、人数、内存、CPU，可直接启停。
- 点「进入」才看细节：控制台、文件、模组、地图、备份、设置。

### 开服与看服

- 把已经存在的服务端目录接管进来，文件不动。
- 启动、停止、强杀；停止走 `stop`，世界正常存盘。
- 实时控制台，日志会同时存到面板的数据目录，重启后还能翻。
- 控制台按级别着色，ERROR 红、WARN 黄、DEBUG 灰，玩家进出单独标色。
- 控制台只放行已知命令，避免手滑把服端搞崩。

### 管理与迁移

- 文件浏览与文本编辑，改 `server.properties` 会保留原来的注释并留一份备份。
- 备份世界与配置，一键恢复；默认保留最近 10 份。
- 导出成 zip 下载到本机，或把 zip 传上去覆盖。
- 导入整合包 zip，自动识别 Forge、NeoForge 或原版，自动挑合适的 Java。
- 换盘搬目录，带空间检查与失败回滚。
- 每个服务器单独设 Java、内存、JVM 参数、编码。
- 地图开关、渲染线程、命令白名单档位这些也按服务器分开设，未改的沿用全局默认。

### 模组

- 列出 `mods/` 里的模组，标出「客户端专用」「两侧都要」「未知」。
- 一键启用或停用，靠改后缀实现，服务端不受影响。
- 在线查询模组信息，判断服务端到底需不需要装。

### 地图

- 接 BlueMap，直接读你现有的世界文件，不复制不移动。
- `/map/` 走面板访问，不用另外暴露端口。
- 显示在线玩家位置（需要服端开 RCON）。
- 在地图上加标记，写进 BlueMap 配置。
- 生成只读共享链接，给朋友看，有有效期。

### 安全

- 登录加两步验证：手机扫码、终端出码、一次性恢复码三种都行。
- 连续登录失败会锁定；所有操作进审计，可查。
- 对外暴露分三档，公网档必须开启两步验证并手写确认短语。
- 防 CSRF、防跨站 WebSocket、限制 JVM 参数与命令。

### 界面与反馈

- 导入、导出、备份这类耗时操作都有进度条，导出与备份可以中途取消。
- 操作结果用右下角提示条，不再弹窗打断。
- 深色与浅色主题切换；想改细节写 `data/theme.css`，不用改代码。
- 整个界面用 JetBrains Mono，字体已内嵌。

### 群里查状态

给 QQ 机器人一个只读令牌，就能查在线人数、玩家名单、最近事件。每群每分钟限 10 次，每人 1 次。

## 安装

### 直接用发布包（不需要 Python）

```powershell
.\hoshi.exe serve
```

第一次启动会打印管理员密码，浏览器打开 `http://127.0.0.1:25566` 登录。

### 从源码

```bash
git clone git@github.com:OverFlame/hoshi_panel.git
cd hoshi_panel
uv venv --python 3.12
uv pip install -e .
uv run python -m hoshi
```

## 需要什么

| 项 | 要求 |
|---|---|
| 系统 | Windows 10 及以上，或 Linux |
| 面板本身 | 发布包不需要装 Python；源码运行需要 Python 3.12 |
| 服务器 | 已有一个能跑的服务端目录，带 Java |
| Java 版本 | 1.20.5 与 1.21+ 用 21；1.18 到 1.20.4 用 17 到 21；更老的用 8 到 16 |
| 资源占用 | 面板空载约 45 MB 内存，几乎不占 CPU |

## 文档

| 文件 | 内容 |
|---|---|
| [QUICKSTART.md](QUICKSTART.md) | 三分钟跑起来 |
| [docs/使用指南.md](docs/使用指南.md) | 完整手册：装、登录、接服务器、备份、模组、地图、安全、常见问题 |
| [packaging/README.md](packaging/README.md) | 打包、开机自启 |

## 现在还不能做什么

| 项 | 说明 |
|---|---|
| 从零下载安装整合包 | 目前只能接管已有目录，或导入现成的 zip |
| Create 列车显示在地图上 | 需要额外的第三方接口 |
| 定时重启、定时备份 | 还没有 |
| 给别人分配不同权限 | 单人使用，只有一个管理员 |

## 主题与自定义

界面默认 Tabler 深色主题，可在设置里切换深色或浅色。

想改细节，把覆盖样式写到 `data/theme.css`，页面会自动加载，不用重启：

```css
:root{ --hoshi-accent:#ff8800; --tblr-body-font-size:.9rem; }
```

`GET /api/theme` 会返回当前主题、自定义 CSS 地址与可用变量名。

Tabler 本体是 MIT 许可，官网卖的「Premium」是额外的模板、插画、邮件模板等素材，与开源主题库无关，不需要购买。

## 字体

界面使用 JetBrains Mono，已内嵌约 25 KB 的子集，不装字体也能正常显示。许可证 SIL OFL 1.1，全文在 `LICENSES/`。

## 许可

GPL-3.0。把程序发给别人时，请同时提供源码与本文件。字体按 SIL OFL 1.1 分发，全文在 `LICENSES/`。Minecraft 游戏文件与 BlueMap 不在仓库里，请自备。

---

# HoshiLauncher (English)

Manage your Minecraft server from a browser: start and stop it, read the console, send commands, take backups, manage mods, look at the map. One program, one operator, runs in the background.

## Credits

MCSL2 is the starting point, © MCSL开发组 under GPL-3.0. BlueMap and CreateTrainWebAPI are MIT, AstrBot is AGPL-3.0, psutil is BSD-3-Clause, JetBrains Mono and the Nerd Fonts patch are SIL OFL 1.1. See the table above.

## AI Notice

**Documents and code in this repo are largely AI-generated.** Expect factual errors and outdated details. Verify before relying on anything, and back up before destructive steps.

## What it does

Adopt an existing server directory, start and stop it, watch the console live, send allowlisted commands, edit `server.properties`, take and restore backups, export and import zip archives, import modpack zips with automatic loader detection, migrate directories, toggle mods with side detection, and serve a BlueMap map with player positions, markers and read-only share links.

Login supports TOTP with a QR code, terminal codes or recovery codes. There is a login lockout, an audit log, CSRF protection and a command allowlist. A read-only token lets a QQ bot report status and players.

## Install

Release build, no Python needed:

```powershell
.\hoshi.exe serve
```

From source:

```bash
uv venv --python 3.12
uv pip install -e .
uv run python -m hoshi
```

The panel idles around 45 MB of RAM. Use Java 21 for 1.20.5 and newer, Java 17 to 21 for 1.18 to 1.20.4.

## Docs

[QUICKSTART.md](QUICKSTART.md), [docs/使用指南.md](docs/使用指南.md) (Chinese user guide), [packaging/README.md](packaging/README.md).

## Not there yet

Installing a modpack from scratch, Create trains on the map, scheduled restarts and backups, multiple users with separate permissions, and per-server map settings.

## License

GPL-3.0. Ship the source with any binary. Fonts are SIL OFL 1.1, see `LICENSES/`. Minecraft assets and BlueMap are not bundled.
