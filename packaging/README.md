# 打包与部署

面板本体是一个 Python 服务。发布给不装 Python 的人时，用 Nuitka 打成独立目录。

## 三种运行方式

| 方式 | 适用 | 命令 |
|---|---|---|
| 源码运行 | 自己开发 | `uv run python -m hoshi` |
| 独立目录 | 给同学、租用机 | `packaging/build.ps1` 或 `build.sh` |
| 系统服务 | 长期常驻 | 见下面的 systemd 与 NSSM |

## 打 Windows 包

```powershell
uv pip install nuitka
pwsh -File packaging/build.ps1
# 产物：dist\entry.dist\hoshi.exe
```

## 打 Linux 包

```bash
uv pip install nuitka
bash packaging/build.sh
# 产物：dist/entry.dist/hoshi
```

注意：Nuitka 不支持跨平台交叉编译。给 Linux 用就在 Linux 上打，反之亦然。

## 部署到 Linux（systemd）

```bash
sudo useradd -r -s /usr/sbin/nologin hoshi
sudo mkdir -p /opt/hoshi /etc/hoshi /srv/minecraft
sudo cp -r dist/entry.dist/* /opt/hoshi/
sudo cp packaging/systemd/hoshi.service /etc/systemd/system/
sudo chown -R hoshi:hoshi /opt/hoshi /srv/minecraft
sudo systemctl daemon-reload
sudo systemctl enable --now hoshi
```

配置文件放 `/etc/hoshi/hoshi.toml`，数据目录默认 `/opt/hoshi/data`，实例目录建议 `/srv/minecraft`。

单元文件里有几项加固，注意按需改：`ReadWritePaths` 必须包含数据目录与实例目录，`MemoryMax=512M` 只是面板本身的上限。

## 部署到 Windows（NSSM）

```powershell
# 先下载 nssm.exe 放到 PATH
pwsh -File packaging\windows\install-service.ps1 -Root "C:\hoshi" -Config "C:\hoshi\hoshi.toml"
```

卸载：`packaging\windows\uninstall-service.ps1`。

## 发布包

```powershell
pwsh -File packaging/release.ps1 -Version 0.1.0
# 产物：release\hoshi-0.1.0-windows-x64.zip
```

压缩包里放了：程序目录、`LICENSE`、`NOTICE.md`、`QUICKSTART.md`、使用指南、systemd 单元、NSSM 安装脚本。

GPL 要求分发二进制时提供对应源码。做法是在发布页附上仓库地址与这个 tag 的源码 zip。

## 从旧版 MCSL2 迁移

```powershell
hoshi migrate-mcsl2 "D:\MCSL2" --dry-run
hoshi migrate-mcsl2 "D:\MCSL2" --java "C:\Program Files\Zulu\zulu-17\bin\java.exe"
```

它读 `Servers/<名字>/MCSL2ServerConfig.json`，把每个实例登记进来。文件不复制、不移动，旧面板还能继续用同一批目录（但不要同时开着两边跑同一个服）。

迁移时会做三件事：

1. 内存单位换算（`G` 转 `M`）。
2. 编码映射（`gbk` 转 `gb18030`）。
3. JVM 参数过白名单，危险的丢掉并在报告里写明。
