# NOTICE

本仓库（HoshiLauncher / 星岚）是 MCSL2 的二次开发分支，并集成了若干第三方组件的设计思路或运行期依赖。这里记录来源、许可与改动。

## 上游

| 项 | 值 |
|---|---|
| 项目 | MCServerLauncher 2（MCSL2） |
| 仓库 | https://github.com/MCSLTeam/MCSL2 |
| 基线 tag | `v2.3.1.0` |
| 基线 commit | `78dac1e6127ca72d751f4a7c76050973138dcb39` |
| 版权 | © 2022 - 2026 MCSL开发组 |
| 许可 | GPL-3.0，仓库内 `LICENSE` 为上游原文 |

上游 `LICENSE` 末尾附有一段自定义条款，原文如下：

```
                      ADDITIONNAL AGREEMENTS
  Anyone who has not been terminated by the MCSL2 development team can
conduct secondary development based on MCSL2.

                          TERMINATED LIST
  1. Yes MineCraft Launcher, link: https://github.com/xiaoshuaiyo/Yes-MineCraft-Launcher ;
  2. MSL-X, link: https://mslx.fun or https://github.com/MSLXTeam/MSL-X ;
```

本仓库的 `LICENSE` 只保留 GPL-3.0 正文，上述条款在此记录，不改其内容。本仓库按 GPL-3.0 履行开源义务。

## 本项目的改动

1. 从 PyQt5 桌面程序改写为常驻服务 + 浏览器控制台。
2. 实例模型增加启动方式抽象，下载层重写，模组侧别判定，目录迁移。
3. 地图采用 BlueMap + CreateTrainWebAPI 组合。
4. 面板界面、认证、配置系统均为新写，不沿用上游 Qt 代码。

## 第三方组件

| 组件 | 用途 | 许可 | 来源 |
|---|---|---|---|
| BlueMap | 三维网页地图渲染 | MIT | https://github.com/BlueMap-Minecraft/BlueMap |
| CreateTrainWebAPI | Create 列车与轨道数据接口 | MIT | https://github.com/BeneHenke/CreateTrainWebAPI |
| Create BlueMap | 备选：Create 车厢渲染 | MIT | https://github.com/Szedann/create-bluemap |
| AstrBot | QQ bot 框架（插件宿主） | AGPL-3.0 | https://github.com/AstrBotDevs/AstrBot |
| Create | 机械动力模组，列车数据来源 | MIT | https://github.com/Creators-of-Create/Create |
| mc-download-guide | 下载链路实测与方法参考 | 见原仓库 | 本地文档，作者未公开托管 |
| Python / aiohttp | 运行时与 HTTP | PSF / Apache-2.0 | https://www.python.org、https://docs.aiohttp.org |
| Modrinth API | 模组元数据与侧别判定 | 服务条款 | https://docs.modrinth.com |
| BMCLAPI | Minecraft 资源镜像 | 服务条款 | https://bmclapi2.bangbang93.com |
| psutil | 进程与主机指标（内存、CPU） | BSD-3-Clause | https://github.com/giampaolo/psutil |
| JetBrains Mono | 界面等宽字体 | SIL OFL 1.1 | https://github.com/JetBrains/JetBrainsMono |
| Nerd Fonts | 字体图标补丁（产出 JetBrainsMono Nerd Font） | 字体 OFL 1.1，补丁脚本 MIT | https://github.com/ryanoasis/nerd-fonts |
| Tabler | 界面主题（v1.0.0-beta20，内嵌 CSS） | MIT | https://github.com/tabler/tabler |

BlueMap 与 CreateTrainWebAPI 不随本仓库分发，由程序在导入实例时按版本矩阵拉取；若你把缓存目录一并分发，需同时附带它们的许可文件。

## 字体的使用与署名

面板界面与控制台使用 JetBrainsMono Nerd Font（由 JetBrains Mono 经 Nerd Fonts 补丁生成）。

| 项 | 内容 |
|---|---|
| 许可证 | SIL Open Font License 1.1，全文见 `LICENSES/OFL-1.1-JetBrainsMono.txt` |
| 版权 | JetBrains Mono：The JetBrains Mono Project Authors；补丁：Ryan L McIntyre |
| 分发方式 | 随程序附带 `woff2` 子集，未修改字形 |
| 限制 | 不得单独售卖字体；OFL 与 GPL-3.0 并存，互不影响 |

只做字形子集化不算修改字形，因此可以保留原字体名。如果有人想二次分发改过的字形，必须换名字。

## 关于 Tabler 的付费部分

Tabler 本体（`tabler.min.css`）是 MIT 许可，可以随本程序分发。官网商店卖的 Premium 是模板、插画、邮件模板等素材，与本项目无关，也没有被使用。

## 不包含的内容

本仓库不包含任何 Minecraft 游戏资源、Mojang 客户端文件或服务端 jar。相关文件由用户自行提供或在运行时下载。使用需自备 Minecraft 正版许可。
