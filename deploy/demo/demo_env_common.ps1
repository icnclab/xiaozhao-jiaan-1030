# 共用模組：建立隔離展示環境（ltc_demo + LINE Mock）所需的環境變數。
# 只在目前 PowerShell 程序記憶體內設定 $env:*，不寫入檔案、不印出密碼／連線字串。
# DATABASE_URL 的帳號密碼沿用專題 .env 的 TEST_DATABASE_URL，只把資料庫名稱換成 ltc_demo，
# 與正式庫 ltc_clean、pytest 用的 ltc_test 完全分開，避免互相污染。
$ErrorActionPreference = 'Stop'
$script:RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$script:Backend = Join-Path $script:RepoRoot 'backend'
$script:Frontend = Join-Path $script:RepoRoot 'frontend'
$script:RunDir = Join-Path $PSScriptRoot 'run'

function Set-DemoEnvironment {
    $envFile = Join-Path $script:RepoRoot '.env'
    if (-not (Test-Path -LiteralPath $envFile)) { throw "找不到 .env：$envFile" }
    $testUrl = $null
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match '^\s*TEST_DATABASE_URL\s*=\s*(.+)$') {
            $testUrl = ($matches[1] -split '#')[0].Trim()
        }
    }
    if (-not $testUrl) { throw '在 .env 找不到 TEST_DATABASE_URL，無法推導展示庫連線字串' }
    $demoUrl = $testUrl -replace '/[^/]+$', '/ltc_demo'

    $env:DATABASE_URL = $demoUrl
    $env:APP_ENV = 'development'
    $env:LINE_MODE = 'mock'
    $env:PUBLIC_BASE_URL = 'http://127.0.0.1:8151'
    $env:DATA_DIR = Join-Path $script:RepoRoot 'data_demo'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:LLM_PROVIDER = 'ollama'
    $env:EMBEDDING_PROVIDER = 'ollama'
    # 緊急通報 LINE Mock 派送旗標：正式環境 .env 完全沒有設定這個變數，正式庫行為不受影響；
    # 60/180 秒時限仍待嘉安核准為正式政策，這裡只用於展示串接驗證。
    $env:JIAAN_EMERGENCY_LINE_DISPATCH = 'on'

    # 安全檢查：強制限定展示庫名稱必須是 ltc_demo，避免設定錯誤時誤連正式庫 ltc_clean。
    $dbName = ([Uri]$demoUrl).AbsolutePath.TrimStart('/')
    if ($dbName -ne 'ltc_demo') {
        throw "安全檢查失敗：DATABASE_URL 指向資料庫「$dbName」，非 ltc_demo，已中止啟動"
    }
}

function Test-PortListening([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Get-DemoOwnedProcess([string]$Kind) {
    New-Item -ItemType Directory -Force -Path $script:RunDir | Out-Null
    $pidFile = Join-Path $script:RunDir "$Kind.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) { return $null }
    $recordedPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    $proc = Get-Process -Id $recordedPid -ErrorAction SilentlyContinue
    if (-not $proc) { return $null }
    $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId=$recordedPid" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdLine -notlike '*app.worker*' -and $cmdLine -notlike '*uvicorn*' -and $cmdLine -notlike '*vite*' -and $cmdLine -notlike '*npm*') {
        return $null
    }
    return $proc
}

function Save-DemoPid([string]$Kind, [int]$ProcessId) {
    New-Item -ItemType Directory -Force -Path $script:RunDir | Out-Null
    Set-Content -LiteralPath (Join-Path $script:RunDir "$Kind.pid") -Value $ProcessId -Encoding ASCII
}
