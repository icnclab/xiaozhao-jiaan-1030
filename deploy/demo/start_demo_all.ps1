# 依序啟動完整隔離展示環境：API（8151）→ Worker（LINE Mock 派送）→ 前端（5180）。
# 每一支子腳本都會先檢查是否已有相同展示服務在執行，不會重複啟動，也完全不會碰正式 API/Worker/DB。
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'start_demo_api.ps1')
& (Join-Path $PSScriptRoot 'start_demo_worker.ps1')
& (Join-Path $PSScriptRoot 'start_demo_frontend.ps1')
Write-Host '完成：如需確認狀態，可查詢 http://127.0.0.1:8151/api/healthz 與 http://127.0.0.1:5180/liff'
