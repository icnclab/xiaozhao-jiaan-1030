# start.ps1 — 啟動 API、worker、（可選）STT sidecar；有埠位守衛，重複執行不會開第二份。
# 用法：powershell -ExecutionPolicy Bypass -File deploy\install\start.ps1 [-NoStt] [-Tunnel]
param([switch]$NoStt, [switch]$Tunnel)
$ErrorActionPreference = "Stop"; [Console]::OutputEncoding = [Text.Encoding]::UTF8
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$vpy = Join-Path $Root "backend\.venv\Scripts\python.exe"; $envSet = Join-Path $Root "backend\scripts\env_set.py"
$Log = Join-Path $Root "logs"; $Run = Join-Path $Root "run"; New-Item -ItemType Directory -Force $Log, $Run | Out-Null
if (Test-Path (Join-Path $Root "bin")) { $env:PATH = (Join-Path $Root "bin") + ";" + $env:PATH }
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
function Listening($port) { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 }
function Launch($name, $exe, $argList, $cwd, $port) {
    if ($port -and (Listening $port)) { Write-Host "  $name：埠 $port 已在使用，略過" -ForegroundColor Yellow; return }
    $p = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $cwd -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$Log\$name.out.log" -RedirectStandardError "$Log\$name.err.log"
    Set-Content -Path "$Run\$name.pid" -Value $p.Id
    Write-Host "  $name：pid $($p.Id)" -ForegroundColor Green
}
function EnvVal($k) { ((& $vpy $envSet --show $k) -replace "^$k=", "").Trim() }
$sttProvider = EnvVal "STT_PROVIDER"; $sttModel = EnvVal "STT_MODEL"; $sttDevice = EnvVal "STT_DEVICE"
if ($sttDevice -match "missing|^$") { $sttDevice = "cuda" }
$apy = Join-Path $Root "venv_asr\Scripts\python.exe"
Write-Host "啟動中（根目錄 $Root）…"
if (-not $NoStt -and $sttProvider -eq "whisper_http" -and (Test-Path $apy)) {
    Launch "stt" $apy @("services\stt_sidecar\server.py", "--port", "8147", "--model", $sttModel, "--device", $sttDevice) $Root 8147
}
Launch "api" $vpy @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8140") (Join-Path $Root "backend") 8140
Launch "worker" $vpy @("-m", "app.worker") (Join-Path $Root "backend") $null
$ok = $false
for ($i = 0; $i -lt 30; $i++) { Start-Sleep 1; try { $h = Invoke-RestMethod http://127.0.0.1:8140/api/healthz -TimeoutSec 2; $ok = $true; break } catch {} }
if ($ok) { Write-Host "API 就緒：modes=$($h.modes | ConvertTo-Json -Compress)" -ForegroundColor Green } else { Write-Host "API 30 秒內未回應，見 logs\api.err.log" -ForegroundColor Red }
Write-Host "照服員端 http://127.0.0.1:8140/liff　督導後台 http://127.0.0.1:8140/admin"
if ($Tunnel) { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "deploy\start_tunnel.ps1") }
