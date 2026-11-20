# 用 NSSM 把面板装成 Windows 服务
# 前置：下载 nssm.exe 放到 PATH，或改 $Nssm 指向它
# 用法（管理员 PowerShell）：
#   pwsh -File packaging\windows\install-service.ps1 -Root "C:\hoshi" -Config "C:\hoshi\hoshi.toml"
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$Config,
    [string]$ServiceName = "HoshiPanel",
    [string]$Nssm = "nssm.exe",
    [string]$Exe = ""
)

$ErrorActionPreference = "Stop"

if (-not $Exe) {
    $candidate = Join-Path $Root "hoshi.exe"
    if (Test-Path $candidate) { $Exe = $candidate }
    else {
        $candidate = Join-Path $Root "entry.dist\hoshi.exe"
        if (Test-Path $candidate) { $Exe = $candidate }
        else { throw "找不到 hoshi.exe，用 -Exe 指定" }
    }
}

& $Nssm install $ServiceName $Exe
& $Nssm set $ServiceName AppParameters "serve --config `"$Config`""
& $Nssm set $ServiceName AppDirectory $Root
& $Nssm set $ServiceName DisplayName "HoshiLauncher 面板"
& $Nssm set $ServiceName Description "Minecraft 服务器网页面板"
& $Nssm set $ServiceName Start SERVICE_AUTO_START
& $Nssm set $ServiceName AppStdout (Join-Path $Root "logs\service.out.log")
& $Nssm set $ServiceName AppStderr (Join-Path $Root "logs\service.err.log")
& $Nssm set $ServiceName AppStopMethodConsole 40000

New-Item -ItemType Directory -Force (Join-Path $Root "logs") | Out-Null
& $Nssm start $ServiceName
Write-Host "已安装并启动服务: $ServiceName"
Write-Host "查看状态: Get-Service $ServiceName"
