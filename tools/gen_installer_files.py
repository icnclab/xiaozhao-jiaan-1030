"""產生 deploy/install/*.ps1（含 UTF-8 BOM，PS 5.1 讀中文所需）與安裝說明。改腳本內容請改這裡再重跑。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deploy" / "install"
OUT.mkdir(parents=True, exist_ok=True)


def ps1(name: str, body: str) -> None:
    (OUT / name).write_bytes(b"\xef\xbb\xbf" + body.lstrip("\n").encode("utf-8"))


ps1("install.ps1", r'''
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
''')

ps1("install_stt.ps1", r'''
# install_stt.ps1 — 安裝本機語音辨識（faster-whisper）到 <Root>\venv_asr（需網路；有 NVIDIA GPU 用 CUDA，否則 CPU）
param([string]$Root = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)), [string]$Model = "")
$ErrorActionPreference = "Stop"; [Console]::OutputEncoding = [Text.Encoding]::UTF8
$vpy = Join-Path $Root "backend\.venv\Scripts\python.exe"
$asr = Join-Path $Root "venv_asr"; $apy = Join-Path $asr "Scripts\python.exe"
if (-not (Test-Path $apy)) { & $vpy -m venv $asr }
$gpu = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
$pkgs = @("faster-whisper>=1.1", "opencc-python-reimplemented")
if ($gpu) { $pkgs += @("nvidia-cublas-cu12", "nvidia-cudnn-cu12") }
& $apy -m pip install --disable-pip-version-check -q --upgrade pip | Out-Null
& $apy -m pip install --disable-pip-version-check -q @pkgs
if ($LASTEXITCODE -ne 0) { throw "faster-whisper 安裝失敗" }
if (-not $Model) { $Model = if ($gpu) { "medium" } else { "small" } }
$dev = if ($gpu) { "cuda" } else { "cpu" }
& $vpy (Join-Path $Root "backend\scripts\env_set.py") STT_PROVIDER=whisper_http "STT_MODEL=$Model" "STT_DEVICE=$dev" | Out-Null
Write-Host "STT 已安裝：model=$Model device=$dev；第一次啟動會自動下載模型（需網路）" -ForegroundColor Green
''')

ps1("start.ps1", r'''
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
''')

ps1("stop.ps1", r'''
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
''')

ps1("status.ps1", r'''
# status.ps1 — 健康檢查
[Console]::OutputEncoding = [Text.Encoding]::UTF8
foreach ($p in @(@{n="API";u="http://127.0.0.1:8140/api/healthz"}, @{n="STT";u="http://127.0.0.1:8147/healthz"}, @{n="Ollama";u="http://127.0.0.1:11434/api/tags"})) {
    try { $r = Invoke-RestMethod $p.u -TimeoutSec 3; $j = ($r | ConvertTo-Json -Compress -Depth 3); Write-Host ("{0,-7} OK   {1}" -f $p.n, $j.Substring(0, [Math]::Min(160, $j.Length))) -ForegroundColor Green }
    catch { Write-Host ("{0,-7} DOWN {1}" -f $p.n, $p.u) -ForegroundColor Yellow }
}
''')

ps1("build_package.ps1", r'''
# build_package.ps1 — 在開發機打包安裝包（離線 wheels＋前端 dist＋ffmpeg）
# 用法：powershell -ExecutionPolicy Bypass -File deploy\install\build_package.ps1 [-OutDir F:\appdata\ltc_care\dist] [-NoFfmpeg]
param([string]$OutDir = "F:\appdata\ltc_care\dist", [switch]$NoFfmpeg, [string]$Python = "python")
$ErrorActionPreference = "Stop"; [Console]::OutputEncoding = [Text.Encoding]::UTF8
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$stamp = Get-Date -Format "yyyyMMdd"
$stage = Join-Path $env:TEMP "ltc_care_pkg"; if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
$pkgRoot = Join-Path $stage "ltc_care"; New-Item -ItemType Directory -Force $pkgRoot, $OutDir | Out-Null

Write-Host "== 前端建置" -ForegroundColor Cyan
Push-Location (Join-Path $Root "frontend"); npm run build | Select-Object -Last 2; Pop-Location

Write-Host "== 匯出相依與下載 wheels（cp311＋cp312，win_amd64）" -ForegroundColor Cyan
Push-Location (Join-Path $Root "backend")
uv export --format requirements-txt --no-dev --no-hashes --no-emit-project -o (Join-Path $Root "deploy\install\requirements.txt") | Out-Null
Pop-Location
$wheels = Join-Path $pkgRoot "wheels"; New-Item -ItemType Directory -Force $wheels | Out-Null
foreach ($pv in "3.11", "3.12") {
    & $Python -m pip download --disable-pip-version-check -q -r (Join-Path $Root "deploy\install\requirements.txt") -d $wheels --only-binary=:all: --platform win_amd64 --python-version $pv --implementation cp
    if ($LASTEXITCODE -ne 0) { throw "pip download 失敗（$pv）" }
}

Write-Host "== 複製程式碼" -ForegroundColor Cyan
$xd = @(".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", "venv_asr", "data", "logs", "run", "wheels", "bin", ".claude")
$xdArgs = @(); foreach ($d in $xd) { $xdArgs += $d }
robocopy $Root $pkgRoot /E /NFL /NDL /NJH /NJS /XD @xdArgs /XF ".env" ".env.*" "*.pyc" "*.log" "*.pid" | Out-Null
Copy-Item (Join-Path $Root ".env.example") (Join-Path $pkgRoot ".env.example") -Force
if (-not $NoFfmpeg) {
    $ff = (Get-Command ffprobe -ErrorAction SilentlyContinue).Source
    if ($ff) {
        $target = (Get-Item $ff).Target; $ffDir = if ($target) { Split-Path "$target" } else { Split-Path $ff }
        New-Item -ItemType Directory -Force (Join-Path $pkgRoot "bin") | Out-Null
        Copy-Item (Join-Path $ffDir "ffmpeg.exe"), (Join-Path $ffDir "ffprobe.exe") (Join-Path $pkgRoot "bin") -Force
        Write-Host "   已內建 ffmpeg/ffprobe（來源 $ffDir）"
    } else { Write-Host "   找不到 ffmpeg，安裝包不含（安裝時改走 winget）" -ForegroundColor Yellow }
}
$commit = (git -C $Root rev-parse --short HEAD 2>$null); if (-not $commit) { $commit = "uncommitted" }
"ltc_care $stamp commit=$commit`nbuilt=$(Get-Date -Format s) on $env:COMPUTERNAME" | Set-Content (Join-Path $pkgRoot "VERSION.txt") -Encoding UTF8
Copy-Item (Join-Path $Root "deploy\install\README_安裝.md") (Join-Path $pkgRoot "README_安裝.md") -Force

Write-Host "== 壓縮" -ForegroundColor Cyan
$zip = Join-Path $OutDir "ltc_care_installer_$stamp.zip"; if (Test-Path $zip) { Remove-Item $zip -Force }
$sevenZip = "C:\Program Files\7-Zip\7z.exe"
if (Test-Path $sevenZip) { & $sevenZip a -tzip -mx=5 -bso0 -bsp0 $zip $pkgRoot | Out-Null } else { Compress-Archive -Path $pkgRoot -DestinationPath $zip }
$mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Get-FileHash $zip -Algorithm SHA256 | ForEach-Object { "$($_.Hash)  $(Split-Path $zip -Leaf)" } | Set-Content "$zip.sha256" -Encoding ascii
Write-Host "完成：$zip（$mb MB）" -ForegroundColor Green
''')

(OUT / "README_安裝.md").write_text(r'''# 長照 AI 照護小幫手「小照」— 安裝說明（實驗室／個人電腦版）

> 解壓後整個資料夾就是系統；資料放在同一資料夾內（`data\`、`logs\`），刪掉資料夾＝解除安裝（資料庫在 Docker volume，另需 `docker compose down -v`）。

## 需要先有的東西

| 項目 | 必要？ | 說明 |
|---|---|---|
| Windows 10/11 64 位元 | 必要 | PowerShell 5.1 以上（內建） |
| Python 3.11 或 3.12 | 必要 | https://www.python.org/downloads/ ，安裝時勾選 **Add python.exe to PATH** |
| Docker Desktop（或 WSL 內已裝 docker） | 必要 | 只用來跑 PostgreSQL＋pgvector 資料庫；https://www.docker.com/products/docker-desktop/ 安裝後**要先打開一次** |
| ffmpeg | 內建 | 安裝包 `bin\` 已附；若沒有，安裝腳本會用 winget 裝 |
| Ollama＋模型 | 選用 | 沒有就走「摘錄模式」（不生成、只摘錄條文、仍附出處）。要用 LLM：安裝 https://ollama.com → `ollama pull gemma4:e4b` |
| NVIDIA GPU | 選用 | 語音辨識加速；沒有 GPU 也能用 CPU 跑 `small` 模型 |
| 網路 | 安裝時不需要 | 除非要裝語音辨識（`-WithStt`）或拉 LLM 模型 |

## 安裝（3 步）

1. 解壓 `ltc_care_installer_<日期>.zip` 到**不含中文與空白**的路徑，例如 `D:\ltc_care`。
2. 在該資料夾按 Shift＋右鍵 →「在此處開啟 PowerShell」，執行：
   ```powershell
   powershell -ExecutionPolicy Bypass -File deploy\install\install.ps1
   ```
   要一併裝語音辨識（需網路，下載約 1.5 GB）：加 `-WithStt`；要順便拉 LLM 模型：加 `-PullModel`。
3. 啟動：
   ```powershell
   powershell -ExecutionPolicy Bypass -File deploy\install\start.ps1
   ```
   照服員端 <http://127.0.0.1:8140/liff>（瀏覽器開發者工具切成手機尺寸較好看）、督導後台 <http://127.0.0.1:8140/admin>。

帳號密碼：安裝時印在畫面上，也存於 `logs\seed.log` 所指的檔案。全部是合成資料、虛構機構。

## 常用指令

| 目的 | 指令 |
|---|---|
| 停止 | `powershell -ExecutionPolicy Bypass -File deploy\install\stop.ps1` |
| 健康檢查 | `powershell -ExecutionPolicy Bypass -File deploy\install\status.ps1` |
| 重建展示資料 | `install.ps1 -ResetDemo` |
| 跑測試 | `backend\.venv\Scripts\python.exe -m pytest backend\tests`（需 db 在跑） |
| 跑 25 題初測 | `backend\.venv\Scripts\python.exe backend\scripts\eval_run.py --llm extractive` |
| 改設定 | 只改 `.env`；改完重跑 `stop.ps1`＋`start.ps1`。改單一鍵可用 `backend\.venv\Scripts\python.exe backend\scripts\env_set.py KEY=value` |

## 接真實 LINE（可選）

見 `docs\line-setup-checklist.md`。Messaging API channel 與 LINE Login channel 建在**同一 provider**；`.env` 填 `LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_LOGIN_CHANNEL_ID`、`LIFF_ID`，`LINE_MODE=real`；需要 HTTPS 公網入口（`start.ps1 -Tunnel` 會開一條 Cloudflare 臨時通道，網址每次不同，須到 LINE Console 更新 webhook 與 LIFF endpoint）。

## 常見問題

- **找不到 Python 3.11 或 3.12**：裝好 Python 後關掉 PowerShell 重開。
- **資料庫未就緒**：Docker Desktop 沒開，或 55432 埠被占用（改 `-DbPort 55433`）。
- **語音上傳回「找不到 ffmpeg」**：`.env` 的 `FFMPEG_DIR` 應指向 `bin\`；或把 ffmpeg 加到 PATH 後重啟。
- **回答都是「摘錄模式」**：沒偵測到 Ollama 模型；裝好後把 `.env` 的 `LLM_PROVIDER` 改 `ollama`。
- **畫面頂端出現「模擬登入／line=mock」**：正常，代表未接真實 LINE。
''', encoding="utf-8")
print("installer files written:", sorted(p.name for p in OUT.iterdir()))
