# 快速开始

三分钟把面板跑起来，接管一个已有的服务端目录。

## 1. 需要什么

| 项 | 要求 |
|---|---|
| 系统 | Windows 10+ 或 Linux |
| Python | 3.12（用发布包则不需要） |
| Java | 17 或 21，看你的服端版本 |

## 2. 启动面板

**用发布包**（不装 Python）：

```powershell
.\hoshi.exe serve
```

**从源码**：

```powershell
git clone git@github.com:OverFlame/hoshi_panel.git
cd hoshi_panel
uv venv --python 3.12
uv pip install -e .
uv run python -m hoshi
```

第一次启动会打印管理员密码，并写入 `data/initial-password.txt`。

## 3. 登录

浏览器打开 `http://127.0.0.1:25566`，账号 `admin`，密码用上面那个。

## 4. 接管已有服务器

命令行先看识别结果：

```powershell
uv run python -m hoshi instances detect "D:\MC\你的服务端"
```

识别没问题就注册：

```powershell
uv run python -m hoshi instances add 我的服 "D:\MC\你的服务端" `
  --java "C:\Program Files\Zulu\zulu-17\bin\java.exe" --max-memory 8192
```

回到页面，左边会出现这个实例。点「启动」开服，「控制台」看日志、发命令。

## 5. 接下来

| 想做什么 | 去哪 |
|---|---|
| 改配置 | 右上角「设置」 |
| 开两步验证 | 设置页「两步验证」，扫码或终端出码 |
| 备份世界 | 实例「备份」页签 |
| 改模组开关 | 实例「模组」页签 |
| 看地图 | 设置里开 `map.enabled`，然后把 BlueMap jar 放进 `data/packages/bluemap/` |
| 给群友查状态 | 设置页「bot 令牌」，配 AstrBot 插件 |

## 6. 别急着开公网

默认只监听 `127.0.0.1`。要远程管理，先用 SSH 隧道：

```powershell
ssh -L 25566:127.0.0.1:25566 你的服务器
```

确实要开放，先读 `docs/使用指南.md` 第 8 节的三条硬性要求。

## 7. 出问题

| 现象 | 先看 |
|---|---|
| 打不开页面 | 启动日志里的「监听」一行，端口是否被占 |
| 启动失败 | 实例目录里有没有核心 jar、`eula.txt` 是否为 true |
| 日志乱码 | 实例 `encoding` 改 `gb18030` |
| 忘了密码 | 服务器上跑 `hoshi reset-password` |
| 其它 | 实例「控制台」里的报错，或 `hoshi instances detect` 的结果 |
