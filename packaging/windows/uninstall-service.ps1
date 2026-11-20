# 卸载 NSSM 服务
param(
    [string]$ServiceName = "HoshiPanel",
    [string]$Nssm = "nssm.exe"
)

$ErrorActionPreference = "Stop"
& $Nssm stop $ServiceName
& $Nssm remove $ServiceName confirm
Write-Host "已移除服务: $ServiceName"
