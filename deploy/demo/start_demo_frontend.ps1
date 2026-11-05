# 啟動隔離展示用前端（Vite dev server，port 5180，代理至展示 API 8151，非正式 8140）。
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'demo_env_common.ps1')

if (Test-PortListening 5180) {
    Write-Host '展示前端（5180）已在執行中，不重複啟動。'
    return
}
$existing = Get-DemoOwnedProcess 'frontend'
if ($existing) {
    Write-Host "展示前端已由先前紀錄的程序執行中（PID=$($existing.Id)），不重複啟動。"
    return
}

$env:VITE_API_PROXY_TARGET = 'http://127.0.0.1:8151'

$proc = Start-Process -FilePath 'cmd.exe' `
    -ArgumentList @('/c', 'npm', 'run', 'dev', '--', '--port', '5180', '--strictPort') `
    -WorkingDirectory $script:Frontend -WindowStyle Hidden -PassThru
Save-DemoPid 'frontend' $proc.Id
Write-Host "展示前端已啟動：PID=$($proc.Id)，代理 API 至 http://127.0.0.1:8151，監聽 http://127.0.0.1:5180"
