# stop.ps1 — 停止 start.ps1 啟動的程序（依 pid 檔；找不到時依埠位）
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot); $Run = Join-Path $Root "run"
foreach ($f in Get-ChildItem $Run -Filter "*.pid" -ErrorAction SilentlyContinue) {
    $id = Get-Content $f.FullName; try { Stop-Process -Id $id -Force -ErrorAction Stop; Write-Host "已停止 $($f.BaseName)（pid $id）" } catch {}
    Remove-Item $f.FullName -Force
}
foreach ($port in 8140, 8147) {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue; Write-Host "已停止埠 $port 的程序" }
}
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match "app\.worker" -and $_.CommandLine -match [regex]::Escape($Root) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host "已停止 worker pid $($_.ProcessId)" }
Write-Host "資料庫容器未停止（要停：docker compose down；資料保留在 volume）"
