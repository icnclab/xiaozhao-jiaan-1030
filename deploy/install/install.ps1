# install.ps1 — 長照 AI 照護小幫手（小照）一鍵安裝（Windows 10/11；PowerShell 5.1 以上）
# 用法（在解壓後的資料夾根目錄）：
#   powershell -ExecutionPolicy Bypass -File deploy\install\install.ps1
#   可選：-DataDir <路徑> -WslDistro <名稱> -DbPort 55432 -WithStt -PullModel -ResetDemo -DatabaseUrl <外部 PG 連線字串>
# 做的事：找 Python → 建 venv（優先離線 wheels）→ 產 .env → 起 pgvector（WSL2 原生 PostgreSQL，apt 安裝，非容器）
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

Step "4/7 資料庫（WSL2 原生 PostgreSQL 16 + pgvector，非 Docker）"
if ($DatabaseUrl) { Ok "使用外部資料庫（須已裝 pgvector 擴充）" }
else {
    if (-not (Get-Command wsl -ErrorAction SilentlyContinue)) { throw "找不到 wsl.exe；請先啟用 WSL2（系統管理員 PowerShell 執行：wsl --install），重開機後再重跑本腳本。" }
    if (-not $WslDistro) {
        $distros = ((wsl -l -q 2>$null) -replace "`0", "") | Where-Object { $_.Trim() }
        if (-not $distros) { throw "找不到任何 WSL distro；請先執行「wsl --install」（預設會裝 Ubuntu），重開機後再重跑本腳本，或用 -WslDistro 指定已有的 distro 名稱。" }
        $WslDistro = "$($distros[0])".Trim()
    }
    Ok "使用 WSL distro：$WslDistro"
    if ((wsl -d $WslDistro -- bash -c "command -v apt-get >/dev/null 2>&1 && echo yes || echo no").Trim() -ne "yes") {
        throw "WSL distro「$WslDistro」不是 Debian/Ubuntu 系（沒有 apt-get），本安裝腳本目前只支援 apt 系。請改用 -WslDistro 指定一個 Ubuntu/Debian distro，或用 -DatabaseUrl 指向既有的 PostgreSQL+pgvector。"
    }
    if ((wsl -d $WslDistro -- bash -c "sudo -n true 2>/dev/null && echo yes || echo no").Trim() -ne "yes") {
        throw "WSL（$WslDistro）目前的使用者執行 sudo 需要密碼，自動安裝無法輸入密碼。請先在該 distro 跑一次（會跳密碼輸入）：echo `"`$USER ALL=(ALL) NOPASSWD:ALL`" | sudo tee /etc/sudoers.d/90-nopasswd；完成後重跑本腳本。"
    }
    $hasPg = (wsl -d $WslDistro -- bash -c "dpkg -s postgresql-16 postgresql-16-pgvector >/dev/null 2>&1 && echo yes || echo no").Trim()
    if ($hasPg -ne "yes") {
        Warn "WSL（$WslDistro）尚未裝 PostgreSQL 16＋pgvector，透過 PGDG 官方套件庫安裝（需網路，約 1-2 分鐘）…"
        # Written to a temp file and run by path (not passed inline as a -c argument):
        # a multi-line string handed straight to `wsl -- bash -c $script` does not survive
        # PowerShell's native-argument marshalling intact (observed: embedded $$ and quotes
        # get corrupted in transit), so every multi-line WSL script here goes through a file.
        $setupScript = @'
set -e
sudo install -d /usr/share/postgresql-common/pgdg
sudo curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
. /etc/os-release
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list >/dev/null
sudo apt-get update -qq
sudo apt-get install -y -qq postgresql-16 postgresql-16-pgvector
'@
        $setupPath = Join-Path $Log "wsl_pg_setup.sh"
        Set-Content -LiteralPath $setupPath -Value $setupScript -Encoding UTF8 -NoNewline
        $wslSetupPath = "/mnt/" + $setupPath.Substring(0,1).ToLower() + ($setupPath.Substring(2) -replace "\\","/")
        wsl -d $WslDistro -- bash "$wslSetupPath"
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL 16＋pgvector 透過 apt 安裝失敗（$WslDistro 需要網路才能連 apt.postgresql.org；見上方 apt 錯誤訊息）" }
        Ok "PostgreSQL 16＋pgvector 已透過 apt 安裝"
    } else { Ok "PostgreSQL 16＋pgvector 已存在，略過安裝" }
    wsl -d $WslDistro -- bash -c "sudo pg_conftool 16 main set port $DbPort" | Out-Null
    wsl -d $WslDistro -- bash -c "sudo service postgresql restart" | Out-Null
    $pgPassSql = $pgPassValue -replace "'", "''"
    $bootstrapSql = @"
DO `$`$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ltc') THEN
    CREATE ROLE ltc LOGIN PASSWORD '$pgPassSql';
  ELSE
    ALTER ROLE ltc PASSWORD '$pgPassSql';
  END IF;
END `$`$;
SELECT 'CREATE DATABASE ltc OWNER ltc' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ltc')\gexec
SELECT 'CREATE DATABASE ltc_test OWNER ltc' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ltc_test')\gexec
\connect ltc
CREATE EXTENSION IF NOT EXISTS vector;
\connect ltc_test
CREATE EXTENSION IF NOT EXISTS vector;
"@
    $sqlPath = Join-Path $Log "wsl_pg_bootstrap.sql"
    Set-Content -LiteralPath $sqlPath -Value $bootstrapSql -Encoding UTF8 -NoNewline
    $wslSqlPath = "/mnt/" + $sqlPath.Substring(0,1).ToLower() + ($sqlPath.Substring(2) -replace "\\","/")
    wsl -d $WslDistro -- bash -c "sudo -u postgres psql -p $DbPort -v ON_ERROR_STOP=1 -f '$wslSqlPath'" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "建立 ltc 使用者／資料庫／pgvector 擴充失敗，見上方 psql 錯誤訊息" }
    Ok "ltc／ltc_test 資料庫與 pgvector 擴充已就位"
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep 3
        $r = & $vpy -c "import psycopg; psycopg.connect('postgresql://ltc:$pgPassValue@127.0.0.1:$DbPort/ltc', connect_timeout=3).close(); print('ok')" 2>$null
        if ("$r" -eq "ok") { $ready = $true; break }
    }
    if (-not $ready) { throw "資料庫 2 分鐘內未就緒；請在 WSL（$WslDistro）用「sudo service postgresql status」檢查，並確認埠 $DbPort 沒被佔用" }
    Ok "資料庫可連線（127.0.0.1:$DbPort，WSL：$WslDistro）"
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
