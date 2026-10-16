# status.ps1 — 健康檢查
[Console]::OutputEncoding = [Text.Encoding]::UTF8
foreach ($p in @(@{n="API";u="http://127.0.0.1:8140/api/healthz"}, @{n="STT";u="http://127.0.0.1:8147/healthz"}, @{n="Ollama";u="http://127.0.0.1:11434/api/tags"})) {
    try { $r = Invoke-RestMethod $p.u -TimeoutSec 3; $j = ($r | ConvertTo-Json -Compress -Depth 3); Write-Host ("{0,-7} OK   {1}" -f $p.n, $j.Substring(0, [Math]::Min(160, $j.Length))) -ForegroundColor Green }
    catch { Write-Host ("{0,-7} DOWN {1}" -f $p.n, $p.u) -ForegroundColor Yellow }
}
