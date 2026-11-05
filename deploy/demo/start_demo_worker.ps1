# 啟動隔離展示用 worker（連線 ltc_demo，非正式庫）；負責緊急通報 LINE Mock 掃描派送。
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'demo_env_common.ps1')

$existing = Get-DemoOwnedProcess 'worker'
if ($existing) {
    Write-Host "展示 Worker 已由先前紀錄的程序執行中（PID=$($existing.Id)），不重複啟動。"
    return
}

Set-DemoEnvironment
if ($env:JIAAN_EMERGENCY_LINE_DISPATCH -ne 'on') { throw '安全檢查失敗：JIAAN_EMERGENCY_LINE_DISPATCH 未設為 on' }
$py = Join-Path $script:Backend '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py)) { throw "找不到展示用 Python：$py" }

$proc = Start-Process -FilePath $py -ArgumentList @('-m', 'app.worker') `
    -WorkingDirectory $script:Backend -WindowStyle Hidden -PassThru
Save-DemoPid 'worker' $proc.Id
Write-Host "展示 Worker 已啟動：PID=$($proc.Id)，連線 ltc_demo，LINE Mock 派送已開啟（JIAAN_EMERGENCY_LINE_DISPATCH=on）"
