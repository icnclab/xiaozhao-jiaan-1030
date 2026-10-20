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
