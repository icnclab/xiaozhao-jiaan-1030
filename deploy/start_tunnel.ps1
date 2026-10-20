# 長照 AI 照護小幫手 — Cloudflare Quick Tunnel（本機實測 LINE 用）
# 把 http://localhost:8140（API＋前端 dist）開成一個臨時 https://xxxx.trycloudflare.com 網址。
# 網址每次重啟都會變；變了就要回 LINE Developers Console 更新 Webhook URL 與 LIFF Endpoint。
# --config 指到獨立的最小設定檔：否則 cloudflared 會自動載入 ~/.cloudflared/config.yml（舊 Named Tunnel 的 ingress，
# 只認 *.icnclab.net、其餘走 http_status:404），trycloudflare 網址進來全部 404 且不會打到 8140。
$ErrorActionPreference = "Stop"
$exe = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$dataDir = "F:\appdata\ltc_care"
$log = Join-Path $dataDir "tunnel.log"
$urlFile = Join-Path $dataDir "tunnel_url.txt"
$envFile = "F:\ltc_care\.env"

if (-not (Test-Path $exe)) { throw "cloudflared not found: $exe" }
New-Item -ItemType Directory -Force $dataDir | Out-Null

if (-not (Get-NetTCPConnection -LocalPort 8140 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host "API (8140) is not listening. Start it first (ltc-api / uvicorn)." -ForegroundColor Red
    exit 1
}

Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
Remove-Item $log, $urlFile -ErrorAction SilentlyContinue

Start-Process -WindowStyle Hidden -FilePath $exe `
    -ArgumentList "tunnel", "--config", (Join-Path $dataDir "cloudflared.yml"), "--url", "http://localhost:8140" `
    -RedirectStandardError $log -RedirectStandardOutput (Join-Path $dataDir "tunnel.out.log")

$url = $null
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value; break }
    }
}
if (-not $url) { Write-Host "No public URL found; check $log" -ForegroundColor Red; exit 1 }

Set-Content -Path $urlFile -Value $url -Encoding ascii

# 把 PUBLIC_BASE_URL 寫進 .env（TTS 音訊 URL 與 LIFF 連結需要 HTTPS 公網位址）。
# 不用 PowerShell 直接讀寫 .env：實測 [IO.File]::ReadAllText 曾回傳空字串並把整個 .env 清空；
# 改走 backend/scripts/env_set.py（內容過短會拒絕修改，且只改該一行）。
$python = "F:\ltc_care\backend\.venv\Scripts\python.exe"
& $python "F:\ltc_care\backend\scripts\env_set.py" "PUBLIC_BASE_URL=$url"
if ($LASTEXITCODE -ne 0) { Write-Host "env_set failed; set PUBLIC_BASE_URL=$url manually." -ForegroundColor Red }

Write-Host ""
Write-Host "Public URL: $url" -ForegroundColor Yellow
Write-Host "  Webhook URL  (Messaging API channel): $url/api/line/webhook"
Write-Host "  LIFF Endpoint (LINE Login channel):    $url/liff"
Write-Host "  Admin:                                $url/admin"
Write-Host ""
Write-Host "PUBLIC_BASE_URL in .env updated. Restart api and worker so they pick it up." -ForegroundColor Cyan
Write-Host "Then: cd F:\ltc_care\backend; uv run python scripts/line_preflight.py --set-webhook --test-webhook"
