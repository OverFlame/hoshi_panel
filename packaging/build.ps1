# 打包成 Windows 独立目录（onedir）
# 用法：pwsh -File packaging/build.ps1
param(
    [string]$Python = ".venv\Scripts\python.exe",
    [string]$Output = "dist"
)

$ErrorActionPreference = "Stop"
# 中文 Windows 上 Nuitka 读 .pth 会用 GBK，强制 UTF-8 避免解码失败
$env:PYTHONUTF8 = "1"
Set-Location (Split-Path $PSScriptRoot -Parent)

& $Python -m nuitka --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "先安装 Nuitka: uv pip install nuitka"
    exit 1
}

& $Python -m nuitka `
    --standalone `
    --assume-yes-for-downloads `
    --output-dir=$Output `
    --output-filename=hoshi.exe `
    --windows-console-mode=force `
    --include-package=hoshi `
    --nofollow-import-to=pytest,tests `
    --noinclude-pytest-mode=nofollow `
    packaging/entry.py

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "产物: $Output\entry.dist\hoshi.exe"
Write-Host "把 hoshi.toml 与 data 目录放在同一层即可运行"
