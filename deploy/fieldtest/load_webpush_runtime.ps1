# Local protected Web Push runtime. Do NOT print secrets or turn dispatch on.
$ErrorActionPreference = 'Stop'
$secretRoot = Join-Path $PSScriptRoot '.local_webpush_secrets'
$privatePath = Join-Path $secretRoot 'vapid_private.pem'
$publicPath = Join-Path $secretRoot 'vapid_public.txt'
$keyPath = Join-Path $secretRoot 'subscription_fernet.key'
foreach ($p in @($privatePath,$publicPath,$keyPath)) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw 'WEBPUSH_RUNTIME_SECRET_MISSING' }
}
$env:JIAAN_VAPID_PRIVATE_KEY = (Get-Content -LiteralPath $privatePath -Raw -Encoding UTF8).Trim()
$env:JIAAN_VAPID_PUBLIC_KEY = (Get-Content -LiteralPath $publicPath -Raw -Encoding UTF8).Trim()
$env:JIAAN_VAPID_SUBJECT = 'mailto:icnclab115@gmail.com'
$env:JIAAN_WEBPUSH_SUBSCRIPTION_KEY = (Get-Content -LiteralPath $keyPath -Raw -Encoding UTF8).Trim()
$env:JIAAN_WEBPUSH_DISPATCH = 'off'
$env:JIAAN_EMERGENCY_LINE_DISPATCH = 'off'
