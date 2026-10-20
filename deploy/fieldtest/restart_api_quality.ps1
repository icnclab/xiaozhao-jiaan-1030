[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'status_jiaan.ps1') -Library
$recordFile = Join-Path $script:RunDir 'api.json'
$lock = $null
try {
    $lock = [IO.File]::Open((Join-Path $script:RunDir 'launcher.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $record = Get-Content -LiteralPath $recordFile -Raw | ConvertFrom-Json
    $spec = Get-LaunchSpec 'api'
    if ($record.Project -ine $script:Root -or $record.Kind -ne 'api' -or $record.Encoded -cne $spec.Encoded) { throw 'API ownership record mismatch' }
    $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $owner = $all | Where-Object ProcessId -eq $record.PID | Select-Object -First 1
    $expectedExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    if (-not $owner -or $owner.ExecutablePath -ine $expectedExe -or $owner.CommandLine -notlike "* $($spec.Encoded)*" -or
        [math]::Abs(($owner.CreationDate.ToUniversalTime() - ([datetime]$record.Started).ToUniversalTime()).TotalMilliseconds) -gt 1) { throw 'API owner identity mismatch' }
    $apis = @(Get-AaProcesses 'api')
    if (-not (Test-AaPort 8140 $apis)) { throw '8140 is not the verified aa API' }
    $health = Get-HttpJson 'http://127.0.0.1:8140/api/healthz'
    if (-not $health -or $health.database_name -ne 'ltc_clean') { throw 'Runtime is not ltc_clean' }
    $children = @(); $parents = @([int]$owner.ProcessId)
    do {
        $next = @($all | Where-Object { $_.ParentProcessId -in $parents })
        $children += $next; $parents = @($next | ForEach-Object { [int]$_.ProcessId })
    } while ($parents.Count)
    if (-not $children.Count) { throw 'API descendants missing' }
    foreach ($child in $children) {
        if ($child.Name -eq 'conhost.exe' -and $child.ParentProcessId -eq $owner.ProcessId -and
            $child.ExecutablePath -ieq "$env:SystemRoot\System32\conhost.exe") { continue }
        if ($child.Name -ne 'python.exe' -or -not $child.CommandLine -or $child.CommandLine -notmatch 'uvicorn\s+app\.main:app') { throw 'Unexpected API descendant' }
    }
    $targets = @($children | Where-Object Name -eq 'python.exe')
    [array]::Reverse($targets)
    $targets += @($owner)
    $pinned = @()
    foreach ($target in $targets) {
        $live = Get-Process -Id $target.ProcessId -ErrorAction Stop
        if ([math]::Abs(($live.StartTime.ToUniversalTime() - $target.CreationDate.ToUniversalTime()).TotalMilliseconds) -gt 1) { throw 'Process identity changed' }
        $pinned += $live
    }
    foreach ($live in $pinned) {
        if (-not $live.HasExited) { Stop-Process -InputObject $live -ErrorAction Stop }
    }
    $deadline = (Get-Date).AddSeconds(10)
    while (@(Get-PortOwner 8140).Count -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 250 }
    if (@(Get-PortOwner 8140).Count) { throw '8140 remains occupied; refusing duplicate launch' }
    $process = Start-Process -FilePath $expectedExe -ArgumentList @('-NoProfile', '-NonInteractive', '-EncodedCommand', $spec.Encoded) -WindowStyle Hidden -PassThru
    [ordered]@{ Project=$script:Root; Kind='api'; PID=$process.Id; Started=$process.StartTime.ToUniversalTime().ToString('o'); Encoded=$spec.Encoded } |
        ConvertTo-Json | Set-Content -LiteralPath $recordFile -Encoding UTF8
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Seconds 2
        $health = Get-HttpJson 'http://127.0.0.1:8140/api/healthz'
        $contract = Get-HttpJson 'http://127.0.0.1:8140/api/openapi.json'
        if ($health -and $health.database_name -eq 'ltc_clean' -and $contract -and $contract.paths.PSObject.Properties['/api/quality/feedback']) {
            Write-Host 'PASS: aa API reloaded quality endpoints; ltc_clean retained; worker/STT/LINE settings/Tailscale untouched.'
            exit 0
        }
    } while ((Get-Date) -lt $deadline)
    throw 'API health or quality endpoint verification failed'
} finally { if ($lock) { $lock.Dispose() } }
