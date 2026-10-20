# install.ps1 — 長照 AI 照護小幫手（小照）一鍵安裝（Windows 10/11；PowerShell 5.1 以上）
# 用法（在解壓後的資料夾根目錄）：
#   powershell -ExecutionPolicy Bypass -File deploy\install\install.ps1
#   可選：-DataDir <路徑> -WslDistro <名稱> -DbPort 55432 -WithStt -PullModel -ResetDemo -DatabaseUrl <外部 PG 連線字串>
# 做的事：找 Python → 建 venv（優先離線 wheels）→ 產 .env → 起 pgvector（Docker Desktop 或 WSL 內 docker）
#         → migration → 合成展示資料 → 偵測 Ollama／SAPI／ffmpeg 決定 provider。
param(
    [string]$DataDir = "",
    [string]$WslDistro = "",
    [int]$DbPort = 55432,
    [switch]$WithStt,
    [switch]$PullModel,
    [switch]$ResetDemo,
    [string]$DatabaseUrl = ""
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $DataDir) { $DataDir = Join-Path $Root "data" }
$Log = Join-Path $Root "logs"; New-Item -ItemType Directory -Force $Log, $DataDir | Out-Null
function Native($cmdline, $log) {
    # PS 5.1 對原生程式的 2>&1 會把 stderr 包成 NativeCommandError（alembic 的 INFO 走 stderr），改由 cmd 重導到檔案
    & cmd /c "$cmdline > `"$log`" 2>&1"
    return $LASTEXITCODE
}
function Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
function Ok($t) { Write-Host "   OK  $t" -ForegroundColor Green }
function Warn($t) { Write-Host "   !!  $t" -ForegroundColor Yellow }

Step "1/7 Python 與後端相依"
$py = $null; $pyver = ""
foreach ($cand in @("py -3.12", "py -3.11", "python")) {
    try {
        $v = (& cmd /c "$cand -c `"import sys;print(sys.version_info[0],sys.version_info[1])`" 2>nul" | Out-String).Trim()
        if ($v -match "^3 (11|12)$") { $py = $cand; $pyver = $v; break }
    } catch {}
}
if (-not $py) { throw "找不到 Python 3.11 或 3.12。請先安裝 https://www.python.org/downloads/ （勾選 Add to PATH）後重跑。" }
Ok "使用 $py（$pyver）"
$venv = Join-Path $Root "backend\.venv"; $vpy = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $vpy)) { & cmd /c "$py -m venv `"$venv`"" | Out-Null }
& $vpy -m pip install --disable-pip-version-check -q --upgrade pip 2>&1 | Out-Null
$req = Join-Path $Root "deploy\install\requirements.txt"; $wheels = Join-Path $Root "wheels"
$installed = $false
if (Test-Path $wheels) {
    $rc = Native "`"$vpy`" -m pip install --disable-pip-version-check -q --no-index --find-links `"$wheels`" -r `"$req`"" "$Log\pip_install.log"
    if ($rc -eq 0) { $installed = $true; Ok "後端相依已從離線 wheels 安裝" } else { Warn "離線 wheels 安裝失敗，改為線上安裝（見 logs\pip_install.log）" }
}
if (-not $installed) {
    $rc = Native "`"$vpy`" -m pip install --disable-pip-version-check -q -r `"$req`"" "$Log\pip_install.log"
    if ($rc -ne 0) { throw "pip 安裝失敗，見 logs\pip_install.log" }
    Ok "後端相依已線上安裝"
}

Step "2/7 ffmpeg"
$bin = Join-Path $Root "bin"; $ffmpegDir = ""
if (Test-Path (Join-Path $bin "ffprobe.exe")) { $ffmpegDir = $bin; Ok "使用安裝包內建 bin\ffmpeg" }
elseif (Get-Command ffprobe -ErrorAction SilentlyContinue) { Ok "使用系統 PATH 上的 ffmpeg" }
else {
    Warn "找不到 ffmpeg，嘗試 winget 安裝（需網路）…"
    try { winget install -e --id Gyan.FFmpeg.Essentials --accept-source-agreements --accept-package-agreements | Out-Null; Ok "winget 已安裝 ffmpeg（新開視窗後才在 PATH）" }
    catch { Warn "ffmpeg 未安裝：語音功能無法使用，文字問答不受影響。請手動安裝後重跑。" }
}

Step "3/7 設定檔 .env"
$envFile = Join-Path $Root ".env"; $envSet = Join-Path $Root "backend\scripts\env_set.py"
if (-not (Test-Path $envFile)) { & $vpy (Join-Path $Root "backend\scripts\gen_env.py") | Out-Null; Ok "已產生 .env（隨機密鑰）" } else { Ok ".env 已存在，沿用（密鑰不變）" }
$pgPassValue = ((Get-Content $envFile -Encoding UTF8 | Where-Object { $_ -match "^POSTGRES_PASSWORD=" }) -replace "^POSTGRES_PASSWORD=", "").Trim()
$sets = @("DATA_DIR=$($DataDir -replace '\\','/')", "DB_PORT=$DbPort", "LINE_MODE=mock", "APP_ENV=dev")
if ($DatabaseUrl) { $sets += "DATABASE_URL=$DatabaseUrl" }
else { $sets += "DATABASE_URL=postgresql+psycopg://ltc:$pgPassValue@127.0.0.1:$DbPort/ltc"; $sets += "TEST_DATABASE_URL=postgresql+psycopg://ltc:$pgPassValue@127.0.0.1:$DbPort/ltc_test" }
if ($ffmpegDir) { $sets += "FFMPEG_DIR=$($ffmpegDir -replace '\\','/')" }
& $vpy $envSet @sets | Out-Null

Step "4/7 資料庫（PostgreSQL 16 + pgvector）"
$compose = Join-Path $Root "docker-compose.yml"
if ($DatabaseUrl) { Ok "使用外部資料庫（須已裝 pgvector 擴充）" }
else {
    $dockerCmd = $null
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        try { docker info 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $dockerCmd = "desktop" } } catch {}
    }
    if (-not $dockerCmd) {
        $distros = if ($WslDistro) { @($WslDistro) } else { ((wsl -l -q 2>$null) -replace "`0", "") | Where-Object { $_.Trim() } }
        foreach ($d in $distros) {
            $d = "$d".Trim(); if (-not $d) { continue }
            $t = wsl -d $d -- bash -lc "docker compose version >/dev/null 2>&1 && echo yes" 2>$null
            if ("$t" -match "yes") { $dockerCmd = "wsl"; $WslDistro = $d; break }
        }
    }
    if (-not $dockerCmd) { throw "找不到可用的 Docker（Docker Desktop 未啟動，或沒有裝了 docker 的 WSL distro）。請安裝並啟動 Docker Desktop 後重跑，或用 -DatabaseUrl 指向既有的 PostgreSQL+pgvector。" }
    if ($dockerCmd -eq "desktop") { docker compose -f "$compose" up -d db | Out-Null; Ok "Docker Desktop：db 容器已啟動" }
    else {
        $wslPath = "/mnt/" + $compose.Substring(0,1).ToLower() + ($compose.Substring(2) -replace "\\", "/")
        wsl -d $WslDistro -- bash -lc "docker compose -f '$wslPath' up -d db" | Out-Null
        Ok "WSL（$WslDistro）：db 容器已啟動"
    }
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep 3
        $r = & $vpy -c "import psycopg; psycopg.connect('postgresql://ltc:$pgPassValue@127.0.0.1:$DbPort/ltc', connect_timeout=3).close(); print('ok')" 2>$null
        if ("$r" -eq "ok") { $ready = $true; break }
    }
    if (-not $ready) { throw "資料庫 2 分鐘內未就緒；請檢查 docker compose ps 與埠 $DbPort" }
    Ok "資料庫可連線（127.0.0.1:$DbPort）"
}

Step "5/7 Migration"
Push-Location (Join-Path $Root "backend")
$env:PYTHONUTF8 = "1"
$rc = Native "`"$vpy`" -m alembic upgrade head" "$Log/alembic.log"
if ($rc -ne 0) { Pop-Location; throw "alembic 失敗，見 logs\alembic.log" }
if (-not $DatabaseUrl) {
    $env:ALEMBIC_DATABASE_URL = "postgresql+psycopg://ltc:$pgPassValue@127.0.0.1:$DbPort/ltc_test"
    Native "`"$vpy`" -m alembic upgrade head" "$Log/alembic_test.log" | Out-Null; Remove-Item Env:ALEMBIC_DATABASE_URL
}
Ok "資料表已建立／更新"

Step "6/7 合成展示資料"
$hasOrg = (& $vpy -c "from sqlalchemy import text; from app.db import new_session; s=new_session(); print(s.execute(text('select count(*) from organizations')).scalar())" | Out-String).Trim()
if ("$hasOrg" -eq "0" -or $ResetDemo) {
    Native "`"$vpy`" scripts\seed_demo.py --reset" "$Log\seed.log" | Out-Null
    Get-Content "$Log\seed.log" -Encoding UTF8 | Select-Object -Last 1
    Ok "合成資料已建立（帳號密碼：logs\seed.log 所示檔案）"
} else { Ok "資料庫已有資料，略過 seed（要重建加 -ResetDemo）" }
Pop-Location

Step "7/7 推論 provider 偵測"
$llmModel = ((& $vpy $envSet --show LLM_MODEL) -replace "^LLM_MODEL=", "").Trim()
$ollama = $null; try { $ollama = Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 3 } catch {}
if ($ollama -and ($ollama.models | Where-Object { $_.name -eq $llmModel })) { & $vpy $envSet LLM_PROVIDER=ollama | Out-Null; Ok "LLM：Ollama 已有 $llmModel" }
elseif ((Get-Command ollama -ErrorAction SilentlyContinue) -and $PullModel) { ollama pull $llmModel; & $vpy $envSet LLM_PROVIDER=ollama | Out-Null; Ok "LLM：已拉取 $llmModel" }
else { & $vpy $envSet LLM_PROVIDER=extractive | Out-Null; Warn "LLM：未偵測到 Ollama 模型，改用摘錄模式（extractive；仍附出處）。要用 LLM：安裝 Ollama → ollama pull $llmModel → 重跑本腳本" }
Add-Type -AssemblyName System.Speech
$voices = (New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }
if ($voices -contains "Microsoft Hanhan Desktop") { & $vpy $envSet TTS_PROVIDER=sapi | Out-Null; Ok "TTS：Windows 中文語音（Hanhan）" }
else { & $vpy $envSet TTS_PROVIDER=mock | Out-Null; Warn "TTS：無中文 SAPI 語音，改 mock（Windows 設定→語言→加入中文語音後可改回 sapi）" }
if ($WithStt) { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "install_stt.ps1") -Root $Root }
else {
    $cur = ((& $vpy $envSet --show STT_PROVIDER) -replace "^STT_PROVIDER=", "").Trim()
    if ($cur -ne "whisper_http" -or -not (Test-Path (Join-Path $Root "venv_asr\Scripts\python.exe"))) { & $vpy $envSet STT_PROVIDER=mock | Out-Null; Warn "STT：mock（要真語音辨識加 -WithStt；需網路下載 faster-whisper 與模型）" }
}

Write-Host "`n安裝完成。啟動：powershell -ExecutionPolicy Bypass -File deploy\install\start.ps1" -ForegroundColor Green
Write-Host "照服員端 http://127.0.0.1:8140/liff　督導後台 http://127.0.0.1:8140/admin"
