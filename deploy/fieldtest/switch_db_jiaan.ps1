[CmdletBinding()]
param([ValidateSet('clean','old')][string]$Target='clean', [switch]$CheckOnly)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'status_jiaan.ps1') -Library
$profileTool=Join-Path $script:Root 'tools\clean_db_profile.py'
if ($env:DATABASE_URL -or $env:DATA_DIR) { throw 'Process environment overrides .env; remove these overrides before switching.' }
& $script:BackendPython $profileTool --target $Target --check
if ($LASTEXITCODE -ne 0) { throw 'Target DB/profile preflight failed; nothing switched.' }
if ($CheckOnly) { return }
$lock=$null
try {
    New-Item -ItemType Directory -Force $script:RunDir,$script:LogDir | Out-Null
    $lock=[IO.File]::Open((Join-Path $script:RunDir 'launcher.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    $api=@(Get-AaProcesses 'api'); $worker=@(Get-AaProcesses 'worker')
    if ($api.Count -gt 1 -or $worker.Count -gt 1) { throw 'Multiple aa API/worker processes; refusing ambiguous restart.' }
    if ($api.Count -eq 1 -and -not (Test-AaPort 8140 $api)) { throw '8140 listener is not the verified aa API.' }
    if ($api.Count -eq 0 -and @(Get-PortOwner 8140).Count) { throw 'Unidentified 8140 listener; refusing restart.' }
    $all=@(Get-CimInstance Win32_Process)
    $owned=@()
    foreach ($process in @($api)+@($worker)) {
        $tree=@($process)
        do {
            $more=@($all | Where-Object { $_.ParentProcessId -in @($tree.ProcessId) -and $_.ProcessId -notin @($tree.ProcessId) })
            if ($more.Count -and @($more | Where-Object Name -ne 'python.exe').Count) { throw 'Unexpected descendant; refusing restart.' }
            $tree+= $more
        } while ($more.Count)
        # Children before venv launchers. Never stop any other project's Python.
        [array]::Reverse($tree)
        $owned+=$tree
    }
    & $script:BackendPython $profileTool --target $Target
    if ($LASTEXITCODE -ne 0) { throw 'Profile update failed; services retained.' }
    foreach ($process in $owned) { Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue }
    $deadline=(Get-Date).AddSeconds(20)
    while (@(Get-PortOwner 8140).Count -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
    if (@(Get-PortOwner 8140).Count) { throw '8140 still occupied; no duplicate process started. Use protected .env backup to recover.' }
    foreach ($kind in 'api','worker') {
        if (@(Get-AaProcesses $kind).Count) { throw 'Old aa process remains; no duplicate launch.' }
        $spec=Get-LaunchSpec $kind
        $process=Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList @('-NoProfile','-NonInteractive','-EncodedCommand',$spec.Encoded) -WindowStyle Hidden -PassThru
        [ordered]@{Project=$script:Root;Kind=$kind;PID=$process.Id;Started=$process.StartTime.ToUniversalTime().ToString('o');Encoded=$spec.Encoded} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:RunDir "$kind.json") -Encoding UTF8
    }
    $deadline=(Get-Date).AddSeconds(50)
    do {
        Start-Sleep -Seconds 2
        $h=Get-HttpJson 'http://127.0.0.1:8140/api/healthz'
        if ($h.db -eq 'ok' -and $null -ne $h.worker_heartbeat_age_sec -and $h.worker_heartbeat_age_sec -lt 60) { break }
    } while ((Get-Date) -lt $deadline)
    if (-not $h -or $h.db -ne 'ok') { throw 'API health failed; retain both DBs and use rollback procedure.' }
} finally { if ($lock) { $lock.Dispose() } }
$rows=@(Get-JiaanStatus)
$rows | Format-Table -AutoSize
$rows | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:Root "docs\clean-db-status-$Target.json") -Encoding UTF8
if (@($rows | Where-Object Result -ne 'PASS').Count) { throw 'Status verification failed; inspect logs and use rollback procedure.' }
Write-Host "DB profile=$Target; all 8 status checks PASS. No Docker/STT/Ollama/Tailscale restart performed."
