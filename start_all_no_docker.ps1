[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = 'C:\aa\ltc_care_installer_20260912\ltc_care'
$BackendPython = Join-Path $Root 'backend\.venv\Scripts\python.exe'
$AsrPython = Join-Path $Root 'venv_asr\Scripts\python.exe'
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force $LogDir | Out-Null

function Log([string]$m) { Write-Host "$(Get-Date -Format s) $m" }

function Get-PortOwner([int]$Port) {
    @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

# 1) WSL native PostgreSQL (replaces docker-compose db; no Docker involved)
Log 'DB: checking WSL native PostgreSQL on 127.0.0.1:55432 ...'
if (-not @(Get-PortOwner 55432).Count) {
    Log 'DB: not listening yet; starting postgres inside WSL (Ubuntu-22.04) ...'
    # /var/run/postgresql is tmpfs and is wiped on every WSL instance restart, so pg_ctl
    # fails with "could not create lock file ... No such file or directory" after a reboot
    # unless it is recreated first. A stale postmaster.pid from an unclean shutdown can also
    # block startup, so clear it before starting.
    wsl -d Ubuntu-22.04 -- bash -c "sudo mkdir -p /var/run/postgresql && sudo chown postgres:postgres /var/run/postgresql && sudo chmod 2775 /var/run/postgresql && if [ -f /var/lib/pgsql16/data/postmaster.pid ] && ! sudo -u postgres kill -0 \$(sudo head -n1 /var/lib/pgsql16/data/postmaster.pid) 2>/dev/null; then sudo rm -f /var/lib/pgsql16/data/postmaster.pid; fi" | Out-Null
    wsl -d Ubuntu-22.04 -- bash -c "sudo -u postgres env LD_LIBRARY_PATH=/opt/pgsql16/icu72/usr/lib/x86_64-linux-gnu /opt/pgsql16/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/pgsql16/data -l /var/lib/pgsql16/pg16.log start" | Out-Null
    Start-Sleep -Seconds 3
}
$deadline = (Get-Date).AddSeconds(30)
do {
    if (@(Get-PortOwner 55432).Count) { Log 'DB: PASS (listening on 55432)'; break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)
if (-not @(Get-PortOwner 55432).Count) { throw 'DB: WSL native PostgreSQL did not come up on 55432' }

# 2) Ollama (model stays resident in GPU VRAM on first real request; this only checks the server)
Log 'Ollama: checking 127.0.0.1:11434 ...'
try {
    Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5 | Out-Null
    Log 'Ollama: PASS (already running)'
} catch {
    Log 'Ollama: not running; launching ollama serve ...'
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) {
        $candidate = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
        if (Test-Path $candidate) { $ollama = Get-Item $candidate } else { throw 'Ollama executable not found' }
    }
    Start-Process -FilePath $ollama.Source -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 3
    Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10 | Out-Null
    Log 'Ollama: PASS (started)'
}

# 3) STT sidecar (CUDA)
Log 'STT: checking 127.0.0.1:8147 ...'
if (-not @(Get-PortOwner 8147).Count) {
    Log 'STT: not running; launching services\stt_sidecar\server.py on CUDA ...'
    Start-Process -FilePath $AsrPython -ArgumentList @('-B',(Join-Path $Root 'services\stt_sidecar\server.py'),'--host','127.0.0.1','--port','8147','--model','medium','--device','cuda') `
        -WorkingDirectory $Root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir 'stt_no_docker.log') -RedirectStandardError (Join-Path $LogDir 'stt_no_docker.err.log') | Out-Null
} else { Log 'STT: retained (port already listening)' }

# 4) Backend API
Log 'API: checking 127.0.0.1:8140 ...'
if (-not @(Get-PortOwner 8140).Count) {
    Log 'API: not running; launching uvicorn app.main:app ...'
    Start-Process -FilePath $BackendPython -ArgumentList @('-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8140') `
        -WorkingDirectory (Join-Path $Root 'backend') -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir 'api_no_docker.log') -RedirectStandardError (Join-Path $LogDir 'api_no_docker.err.log') | Out-Null
} else { Log 'API: retained (port already listening)' }

# 5) Worker
Log 'Worker: launching app.worker (no port; relies on process + heartbeat) ...'
$workerRunning = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -ieq $BackendPython -and $_.CommandLine -match '-m\s+app\.worker' }).Count -gt 0
if (-not $workerRunning) {
    Start-Process -FilePath $BackendPython -ArgumentList @('-B','-m','app.worker') `
        -WorkingDirectory (Join-Path $Root 'backend') -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir 'worker_no_docker.log') -RedirectStandardError (Join-Path $LogDir 'worker_no_docker.err.log') | Out-Null
} else { Log 'Worker: retained (process already running)' }

Start-Sleep -Seconds 5
Log '--- final health check ---'
try {
    $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8140/api/healthz' -TimeoutSec 10
    Log "API healthz: db=$($h.db) worker_heartbeat_age_sec=$($h.worker_heartbeat_age_sec)"
} catch {
    Log "API healthz FAILED: $($_.Exception.Message)"
}
try {
    $s = Invoke-RestMethod -Uri 'http://127.0.0.1:8147/healthz' -TimeoutSec 10
    Log "STT healthz: ok=$($s.ok) device=$($s.device) loaded=$($s.loaded -join ',')"
} catch {
    Log "STT healthz FAILED: $($_.Exception.Message)"
}
Log 'start_all_no_docker.ps1 done. (Docker is not used anywhere in this script.)'
