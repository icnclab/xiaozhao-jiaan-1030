[CmdletBinding()]
param([switch]$AutoStart)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'status_jiaan.ps1') -Library
. (Join-Path $PSScriptRoot 'autostart_common.ps1')
New-Item -ItemType Directory -Force $script:RunDir,$script:LogDir | Out-Null
$lock = $null
function Log-Start([string]$Message) {
    $line = "$(Get-Date -Format s) $Message"
    $path=Join-Path $script:LogDir 'startup.log'
    if((Test-Path $path) -and (Get-Item $path).Length -gt 10MB){Move-Item -LiteralPath $path -Destination ($path+'.1') -Force}
    Add-Content -LiteralPath $path -Value $line -Encoding UTF8
    Write-Host $Message
}
function Wait-Check([scriptblock]$Check,[int]$Seconds=60) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do { if (& $Check) { return $true }; Start-Sleep -Seconds 2 } while ((Get-Date) -lt $deadline)
    return $false
}
function Start-Owned([string]$Kind) {
    $existing = @(Get-AaProcesses $Kind)
    if ($existing.Count) { Log-Start "$Kind retained: existing aa process; no duplicate launch"; return }
    $spec = Get-LaunchSpec $Kind
    $process = Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList @('-NoProfile','-NonInteractive','-EncodedCommand',$spec.Encoded) -WindowStyle Hidden -PassThru
    $record = [ordered]@{Project=$script:Root;Kind=$Kind;PID=$process.Id;Started=$process.StartTime.ToUniversalTime().ToString('o');Encoded=$spec.Encoded}
    $record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:RunDir "$Kind.json") -Encoding UTF8
    Log-Start "$Kind launched; log=$Kind.log"
}
try {
    $lock = [IO.File]::Open((Join-Path $script:RunDir 'launcher.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    foreach($path in $script:BackendPython,$script:AsrPython,$script:Tailscale,(Join-Path $script:Root 'frontend\dist\index.html')) {
        if(-not (Test-Path -LiteralPath $path -PathType Leaf)){ throw 'Required project file or executable missing' }
    }
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if(-not $ollama){ $candidate=Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'; if(Test-Path $candidate){$ollama=Get-Item $candidate}else{throw 'Ollama executable missing'} }
    # Migrated off Docker (2026-11-21): DB is WSL-native PostgreSQL (Ubuntu-22.04, port 55432),
    # the same instance start_all_no_docker.ps1 manages. /var/run/postgresql is tmpfs and is
    # wiped on every WSL instance restart, so pg_ctl needs it recreated (and any stale
    # postmaster.pid from a dead process cleared) before each start attempt.
    Wait-JiaanReady 'DB' {
        @(Get-PortOwner 55432).Count -gt 0
    } {
        Invoke-JiaanNative 'wsl' @('-d','Ubuntu-22.04','--','bash','-c',
            "sudo mkdir -p /var/run/postgresql && sudo chown postgres:postgres /var/run/postgresql && sudo chmod 2775 /var/run/postgresql && if [ -f /var/lib/pgsql16/data/postmaster.pid ] && ! sudo -u postgres kill -0 `$(sudo head -n1 /var/lib/pgsql16/data/postmaster.pid) 2>/dev/null; then sudo rm -f /var/lib/pgsql16/data/postmaster.pid; fi") | Out-Null
        Invoke-JiaanNative 'wsl' @('-d','Ubuntu-22.04','--','bash','-c',
            'sudo -u postgres env LD_LIBRARY_PATH=/opt/pgsql16/icu72/usr/lib/x86_64-linux-gnu /opt/pgsql16/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/pgsql16/data -l /var/lib/pgsql16/pg16.log start') | Out-Null
    } 60 5
    if(-not (Get-HttpJson 'http://127.0.0.1:11434/api/tags')) {
        $ollamaPath = if($ollama.Source){$ollama.Source}else{$ollama.FullName}
        Wait-JiaanReady 'Ollama' { Get-HttpJson 'http://127.0.0.1:11434/api/tags' } {
            if(-not @(Get-PortOwner 11434).Count -and -not @(Get-Process ollama -ErrorAction SilentlyContinue).Count) {
                Start-Process -FilePath $ollamaPath -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
            }
        } 30 10
    }
    Wait-JiaanReady 'Model gemma4:e4b' {
        if(-not @((Get-HttpJson 'http://127.0.0.1:11434/api/tags').models | Where-Object name -eq 'gemma4:e4b').Count){return $false}
        try {
            $m=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/show' -Method Post -ContentType 'application/json' -Body '{"model":"gemma4:e4b"}' -TimeoutSec 15
            return $null -ne $m.model_info
        } catch {return $false}
    } {} 30 10
    foreach($kind in 'stt','api') {
        $port=if($kind -eq 'stt'){8147}else{8140}
        $url="http://127.0.0.1:$port/healthz"; if($kind -eq 'api'){$url="http://127.0.0.1:$port/api/healthz"}
        if(@(Get-PortOwner $port).Count -or @(Get-AaProcesses $kind).Count){Log-Start "$kind retained; existing listener/process requires health validation"}
        else {Log-Start "$kind missing: launching aa process"; Start-Owned $kind}
        Wait-JiaanReady $kind {
            $h=Get-HttpJson $url (Get-InternalHealthHeaders)
            if($kind -eq 'stt'){ $h.ok -and $h.model -eq 'medium' -and $h.device -eq 'cuda' -and 'medium' -in $h.loaded }
            else { $h.db -eq 'ok' -and $h.modes.line -eq 'real' }
        } { if(-not @(Get-PortOwner $port).Count -and -not @(Get-AaProcesses $kind).Count){Start-Owned $kind} } 30 10
    }
    # SOS(8165)/SOS45(8166) autostart. Deliberately placed BEFORE the Worker step below:
    # Worker's own identity check can throw and abort this entire script (see the next
    # block), and SOS/SOS45 depend on neither Worker nor each other, so they must not be
    # starved by an unrelated Worker-step failure. Isolated in its own try/catch: a problem
    # here must never abort api/worker/stt verification, and must never touch 8140/Worker/DB.
    # Kill switch: create deploy/fieldtest/run/.disable_sos_autostart to opt out entirely
    # (e.g. while debugging by hand) without touching this script or the scheduled task.
    $sosDisableFlag = Join-Path $script:RunDir '.disable_sos_autostart'
    if (Test-Path -LiteralPath $sosDisableFlag) {
        Log-Start 'SOS/SOS45 autostart disabled (run\.disable_sos_autostart present); skipping'
    } else {
        foreach ($kind in 'sos','sos45') {
            try {
                $decision = Get-SosStartDecision $kind
                switch ($decision.Action) {
                    'warn_unidentified_occupant' {
                        Log-Start "$kind WARNING: port $($decision.Port) is occupied by a process this launcher cannot verify as its own; refusing to start or claim ownership (manual review required)"
                        continue
                    }
                    'retain' { Log-Start "$kind retained: existing verified aa process; no duplicate launch" }
                    'start' { Log-Start "$kind missing: launching aa process"; Start-Owned $kind }
                }
                Wait-JiaanReady $kind { Test-SosHealthy $kind (Get-InternalHealthHeaders) } {
                    $redecide = Get-SosStartDecision $kind
                    if ($redecide.Action -eq 'start') { Start-Owned $kind }
                } 6 10
            } catch {
                # Bounded retry already exhausted inside Wait-JiaanReady; log and move on.
                # SOS/SOS45 are independent of the core pipeline and must not fail the run.
                Log-Start "$kind FAIL (non-fatal to core services): $($_.Exception.Message)"
            }
        }
    }
    Start-Owned 'worker'
    if(-not (Wait-Check { $h=Get-HttpJson 'http://127.0.0.1:8140/api/healthz'; $null -ne $h.worker_heartbeat_age_sec -and $h.worker_heartbeat_age_sec -ge 0 -and $h.worker_heartbeat_age_sec -lt 60 })){
        if($script:HttpFailures.ContainsKey('http://127.0.0.1:8140/api/healthz')){throw ('Worker heartbeat unverified: API healthz query failed (' + $script:HttpFailures['http://127.0.0.1:8140/api/healthz'] + '); no extra Worker launched')}
        throw 'Worker heartbeat missing/stale; no extra Worker launched'
    }
    if($AutoStart){ Ensure-JiaanTailscale }
    Log-Start 'Startup dependency checks completed.'
} catch { Log-Start "FAIL: $($_.Exception.Message)"; $failed=$true }
finally { if($lock){$lock.Dispose()} }
try { $rows=@(Get-JiaanStatus); $rows|Format-Table -AutoSize; $rows|ForEach-Object {Log-Start "$($_.Service) $($_.Result): $($_.Detail)"}; if($failed -or @($rows|Where-Object Result -eq 'FAIL').Count){exit 1}; exit 0 }
catch {Log-Start 'FAIL: final health checks unavailable'; exit 1}
