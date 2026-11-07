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
    $health = Get-HttpJson 'http://127.0.0.1:8140/api/healthz' (Get-InternalHealthHeaders)
    if (-not $health -or $health.database_name -ne 'ltc_clean') { throw 'Runtime is not ltc_clean' }
    $children = @(); $parents = @([int]$owner.ProcessId)
    do {
        $next = @($all | Where-Object { $_.ParentProcessId -in $parents })
        $children += $next; $parents = @($next | ForEach-Object { [int]$_.ProcessId })
    } while ($parents.Count)
    if (-not $children.Count) { throw 'API descendants missing' }
    # CPython on Windows venv: venv launcher -> base interpreter.
    # Accept exactly that pair, plus at most one direct console host.
    $cfgPath = Join-Path $script:Root 'backend\.venv\pyvenv.cfg'
    $baseCfg = @(Get-Content -LiteralPath $cfgPath | Where-Object { $_ -match '^executable\s*=' })
    if ($baseCfg.Count -ne 1) { throw 'Base interpreter configuration unavailable' }
    $basePython = ($baseCfg[0] -split '=', 2)[1].Trim()
    if (-not (Test-Path -LiteralPath $basePython -PathType Leaf)) { throw 'Base interpreter unavailable' }
    $venvPython = $spec.Exe
    $pythonChildren = @($children | Where-Object { $_.Name -ieq 'python.exe' })
    $launchers = @($pythonChildren | Where-Object {
        $_.ParentProcessId -eq $owner.ProcessId -and $_.ExecutablePath -ieq $venvPython
    })
    if ($launchers.Count -ne 1 -or $pythonChildren.Count -ne 2) { throw 'Unexpected API Python process tree' }
    $launcher = $launchers[0]
    $base = @($pythonChildren | Where-Object {
        $_.ParentProcessId -eq $launcher.ProcessId -and $_.ExecutablePath -ieq $basePython
    })
    if ($base.Count -ne 1) { throw 'Unexpected API base interpreter' }
    $consoleHosts = @($children | Where-Object { $_.Name -ieq 'conhost.exe' })
    if ($consoleHosts.Count -gt 1) { throw 'Unexpected API console count' }
    foreach ($child in $children) {
        if (-not $child.ExecutablePath -or -not $child.CommandLine -or -not $child.CreationDate) { throw 'Incomplete descendant identity' }
        if ($child.CreationDate -lt $owner.CreationDate) { throw 'Unexpected descendant start time' }
        if ($child.Name -ieq 'conhost.exe') {
            if ($child.ParentProcessId -ne $owner.ProcessId -or
                $child.ExecutablePath -ine "$env:SystemRoot\System32\conhost.exe" -or
                @($all | Where-Object { $_.ParentProcessId -eq $child.ProcessId }).Count) {
                throw 'Unexpected console process'
            }
        } elseif ($child.Name -ieq 'python.exe') {
            if ($child.ProcessId -notin @($launcher.ProcessId, $base[0].ProcessId) -or
                $child.CommandLine -notmatch 'uvicorn\s+app\.main:app') { throw 'Unexpected API Python arguments' }
        } else { throw 'Unexpected descendant; refusing stop' }
    }
    if (@($all | Where-Object { $_.ParentProcessId -eq $base[0].ProcessId }).Count) {
        throw 'Unexpected nested base interpreter descendants'
    }
    $targets = @($base[0], $launcher)  # base interpreter, then venv launcher
    $targets += @($owner)
    $pinned = @()
    foreach ($target in $targets) {
        $live = Get-Process -Id $target.ProcessId -ErrorAction Stop
        if ([math]::Abs(($live.StartTime.ToUniversalTime() - $target.CreationDate.ToUniversalTime()).TotalMilliseconds) -gt 1) { throw 'Process identity changed' }
        $pinned += $live
    }
    # Refuse if the tree changed after pinning the checked process identities.
    $fresh = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    foreach ($node in $children) {
        $same = @($fresh | Where-Object { $_.ProcessId -eq $node.ProcessId -and $_.ParentProcessId -eq $node.ParentProcessId -and $_.ExecutablePath -ieq $node.ExecutablePath -and $_.CommandLine -ceq $node.CommandLine })
        if ($same.Count -ne 1) { throw 'Process tree changed before stop' }
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
