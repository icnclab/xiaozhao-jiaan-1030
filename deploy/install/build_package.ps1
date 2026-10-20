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
