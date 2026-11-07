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
    foreach($path in $script:BackendPython,$script:AsrPython,$script:Tailscale,(Join-Path $script:Root 'frontend\dist\index.html'),(Join-Path $script:Root 'docker-compose.yml')) {
        if(-not (Test-Path -LiteralPath $path -PathType Leaf)){ throw 'Required project file or executable missing' }
    }
    $docker = Get-Command docker -ErrorAction Stop
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if(-not $ollama){ $candidate=Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'; if(Test-Path $candidate){$ollama=Get-Item $candidate}else{throw 'Ollama executable missing'} }
    Wait-JiaanReady 'Docker' {
        (Invoke-JiaanNative $docker.Source @('info','--format','{{.ServerVersion}}')).ExitCode -eq 0
    } { Start-JiaanDocker } 30 10
    Push-Location $script:Root
    try {
        # Existing-volume guard: never initialize a replacement empty DB.
        $native = Invoke-JiaanNative $docker.Source @('volume','inspect','ltc_care_ltc_pgdata')
        if($native.ExitCode -ne 0){throw 'Existing aa DB volume missing; refusing to initialize DB'}
        $native = Invoke-JiaanNative $docker.Source @('inspect','ltc_care-db-1')
        $dbRaw = $native.Output
        if($native.ExitCode -ne 0){throw 'Existing aa DB container missing; refusing to initialize a replacement'}
        $dbIdentity = @(($dbRaw -join "`n") | ConvertFrom-Json)[0]
        if($dbIdentity.Config.Labels.'com.docker.compose.project' -ne 'ltc_care' -or
           $dbIdentity.Config.Labels.'com.docker.compose.service' -ne 'db' -or
           -not @($dbIdentity.Mounts | Where-Object {$_.Name -eq 'ltc_care_ltc_pgdata' -and $_.Destination -eq '/var/lib/postgresql/data'}).Count){throw 'aa DB container identity/volume mismatch'}
        Log-Start 'DB: checking existing aa container; compose progress on stderr is not a failure.'
        $native = Invoke-JiaanNative $docker.Source @('compose','-p','ltc_care','up','-d','--no-build','--no-recreate','db')
        Log-Start "DB compose exit=$($native.ExitCode); proceeding to actual container health check"
        if($native.ExitCode -ne 0){throw "aa DB startup failed (exit=$($native.ExitCode)); no raw native output logged"}
    } finally { Pop-Location }
    Wait-JiaanReady 'DB' {
        $n=Invoke-JiaanNative $docker.Source @('inspect','--format','{{.State.Health.Status}}','ltc_care-db-1')
        $n.ExitCode -eq 0 -and ($n.Output -join '').Trim() -eq 'healthy'
    } {} 30 5
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
