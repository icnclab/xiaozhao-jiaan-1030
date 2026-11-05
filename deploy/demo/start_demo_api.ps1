# 啟動隔離展示用 API（port 8151，連線 ltc_demo，非正式庫 ltc_clean）。
# 使用前請先確認 .env 存在且包含 TEST_DATABASE_URL。
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'demo_env_common.ps1')

if (Test-PortListening 8151) {
    Write-Host '展示 API（8151）已在執行中，不重複啟動。'
    return
}
$existing = Get-DemoOwnedProcess 'api'
if ($existing) {
    Write-Host "展示 API 已由先前紀錄的程序執行中（PID=$($existing.Id)），不重複啟動。"
    return
}

Set-DemoEnvironment
$py = Join-Path $script:Backend '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py)) { throw "找不到展示用 Python：$py" }

$proc = Start-Process -FilePath $py `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8151') `
    -WorkingDirectory $script:Backend -WindowStyle Hidden -PassThru
Save-DemoPid 'api' $proc.Id
Write-Host "展示 API 已啟動：PID=$($proc.Id)，連線 ltc_demo，監聽 http://127.0.0.1:8151"
