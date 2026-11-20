# 打发布包
# 前置：先跑 packaging/build.ps1 产出 dist\entry.dist
# 用法：pwsh -File packaging/release.ps1 -Version 0.1.0
param(
    [string]$Version = "0.1.0",
    [string]$Dist = "dist\entry.dist",
    [string]$Out = "release"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path $Dist)) { throw "找不到 $Dist，先运行 packaging/build.ps1" }
New-Item -ItemType Directory -Force $Out | Out-Null

$stage = Join-Path $Out "hoshi-$Version"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $stage | Out-Null

Copy-Item "$Dist\*" $stage -Recurse
Copy-Item LICENSE, NOTICE.md, QUICKSTART.md $stage
Copy-Item "docs\使用指南.md" $stage -ErrorAction SilentlyContinue
Copy-Item "packaging\systemd\hoshi.service" $stage
Copy-Item "packaging\windows\install-service.ps1" $stage

$zip = Join-Path $Out "hoshi-$Version-windows-x64.zip"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal

Write-Host "发布包: $zip"
Get-ChildItem $zip | ForEach-Object { "大小: {0:N1} MB" -f ($_.Length / 1MB) }
Write-Host "GPL 要求：分发二进制时同时提供源码，仓库地址写在 NOTICE.md"
