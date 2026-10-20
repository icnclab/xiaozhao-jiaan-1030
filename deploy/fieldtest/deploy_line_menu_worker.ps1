# Run only from the installed user's elevated Windows PowerShell.
# Default is read-only preflight. -Execute authorizes the existing Worker stop only.
[CmdletBinding()]
param([switch]$Execute)
$ErrorActionPreference='Stop'
function Assert-ProtectedProcesses($Before,$After) {
    foreach($p in $Before){
        $same=@($After|Where-Object {$_.ProcessId -eq $p.ProcessId -and $_.CreationDate -eq $p.CreationDate -and $_.ExecutablePath -ieq $p.ExecutablePath})
        if($same.Count -ne 1){throw "Protected process changed: $($p.Name) PID=$($p.ProcessId)"}
    }
}
try {
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    $principal=New-Object Security.Principal.WindowsPrincipal($identity)
    $expected=New-Object Security.Principal.NTAccount('STUST\icncl')
    if($identity.User.Value -ne $expected.Translate([Security.Principal.SecurityIdentifier]).Value -or
       -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
        throw 'Use elevated Windows PowerShell as STUST\icncl.'
    }
    . (Join-Path $PSScriptRoot 'status_jiaan.ps1') -Library
    # Load validation functions only: do not dot-source the stop script itself.
    $stop=Join-Path $PSScriptRoot 'stop_jiaan.ps1'
    $tokens=$null; $errors=$null
    $ast=[System.Management.Automation.Language.Parser]::ParseFile($stop,[ref]$tokens,[ref]$errors)
    if($errors){throw 'Stop script syntax error'}
    foreach($name in 'Get-VerifiedWorkerTree','Get-WorkerTreeStamp'){
        $fn=@($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)|Where-Object Name -eq $name)
        if($fn.Count -ne 1){throw 'Stop validator unavailable'}
        . ([scriptblock]::Create($fn[0].Extent.Text))
    }
    $cfg=Get-Content -LiteralPath (Join-Path $script:Root 'backend\.venv\pyvenv.cfg')
    $baseLines=@($cfg|Where-Object {$_ -match '^executable\s*='})
    if($baseLines.Count -ne 1){throw 'Base Python configuration unavailable'}
    $basePython=($baseLines[0] -split '=',2)[1].Trim()
    $spec=Get-LaunchSpec 'worker'
    $recordFile=Join-Path $script:RunDir 'worker.json'
    $record=Get-Content -LiteralPath $recordFile -Raw|ConvertFrom-Json
    $all=@(Get-CimInstance Win32_Process)
    $tree=Get-VerifiedWorkerTree $all $record $spec $script:Root $basePython
    $oldStamp=Get-WorkerTreeStamp $tree
    $task=Get-ScheduledTask -TaskName 'Jiaan-Autostart'
    $supervisorPath=Join-Path $PSScriptRoot 'autostart_jiaan.ps1'
    if($task.State -ne 'Running' -or $task.Actions.Count -ne 1 -or
       $task.Actions[0].Execute -ine "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -or
       $task.Actions[0].Arguments -notlike "*-File `"$supervisorPath`"*"){
        throw 'Supervisor task identity/state mismatch'
    }
    $supervisors=@($all|Where-Object {$_.Name -ieq 'powershell.exe' -and $_.ExecutablePath -ieq $task.Actions[0].Execute -and $_.CommandLine -like "*-File `"$supervisorPath`"*"})
    if($supervisors.Count -ne 1){throw 'Supervisor process identity unavailable or ambiguous'}
    $rows=@(Get-JiaanStatus)
    if(@($rows|Where-Object Result -eq 'FAIL').Count){throw 'Preflight health failed'}
    $ps="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    & $ps -NoProfile -ExecutionPolicy Bypass -File $stop -Services worker -WhatIf
    if($LASTEXITCODE -ne 0){throw 'WhatIf refused; no stop attempted'}

    $source=Join-Path $script:Root 'backend\app\line\service.py'
    $sourceHash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    $modified=(Get-Item -LiteralPath $source).LastWriteTimeUtc
    Write-Host "Preflight PASS. service.py SHA256=$sourceHash"
    if(-not $Execute){Write-Host 'Read-only preflight complete; no Worker stopped.'; exit 0}

    # Capture all unrelated Python, Docker, Ollama and WSL processes, plus supervisor.
    $protected=@($all|Where-Object {
        ($_.Name -match 'docker|ollama|wsl|^python\.exe$' -or $_.ProcessId -eq $supervisors[0].ProcessId) -and
        $_.ProcessId -notin $tree.Members.ProcessId
    })
    $docker=(Get-Command docker -ErrorAction Stop).Source
    $dbBefore=Invoke-JiaanNative $docker @('inspect','--format','{{.State.StartedAt}}','ltc_care-db-1')
    if($dbBefore.ExitCode -ne 0){throw 'DB identity read failed'}
    $log=Join-Path $script:LogDir 'worker.log'
    $logLines=if(Test-Path -LiteralPath $log){@(Get-Content -LiteralPath $log).Count}else{0}
    $fresh=Get-VerifiedWorkerTree @(Get-CimInstance Win32_Process) (Get-Content $recordFile -Raw|ConvertFrom-Json) $spec $script:Root $basePython
    if((Get-WorkerTreeStamp $fresh) -cne $oldStamp){throw 'Worker changed during preflight'}
    Assert-ProtectedProcesses $protected @(Get-CimInstance Win32_Process)
    if((Get-ScheduledTask -TaskName 'Jiaan-Autostart').State -ne 'Running'){throw 'Supervisor stopped during preflight'}
    if((Get-FileHash $source -Algorithm SHA256).Hash -ne $sourceHash){throw 'Source changed during preflight'}
    $stoppedAt=(Get-Date).ToUniversalTime()
    & $ps -NoProfile -ExecutionPolicy Bypass -File $stop -Services worker
    if($LASTEXITCODE -ne 0){throw 'Stop not confirmed; no alternative start/stop attempted'}
    $remaining=@(Get-CimInstance Win32_Process)
    foreach($old in $tree.Targets){
        if(@($remaining|Where-Object {$_.ProcessId -eq $old.ProcessId -and $_.CreationDate -eq $old.CreationDate}).Count){throw 'Old Worker still present'}
    }
    Write-Host 'Old Worker stopped. Waiting only for Supervisor (up to 180 seconds).'
    $deadline=(Get-Date).AddSeconds(180); $stable=0; $newStamp=$null; $verified=$false
    do {
        Start-Sleep -Seconds 5
        $now=@(Get-CimInstance Win32_Process)
        Assert-ProtectedProcesses $protected $now
        $workers=@(Get-AaProcesses 'worker')
        if($workers.Count -gt 1){throw 'Multiple Workers; no further actions attempted'}
        if($workers.Count -eq 1){
            $newRecord=Get-Content -LiteralPath $recordFile -Raw|ConvertFrom-Json
            $newTree=Get-VerifiedWorkerTree $now $newRecord $spec $script:Root $basePython
            foreach($node in $newTree.Targets){
                if($node.CreationDate.ToUniversalTime() -le $modified -or $node.CreationDate.ToUniversalTime() -lt $stoppedAt){throw 'New Worker time mismatch'}
            }
            $stamp=Get-WorkerTreeStamp $newTree
            if($newStamp -and $stamp -cne $newStamp){throw 'New Worker restarted again; investigate'}
            $newStamp=$stamp
            $rows=@(Get-JiaanStatus)
            if(@($rows|Where-Object {$_.Service -ne 'WORKER' -and $_.Result -eq 'FAIL'}).Count){throw 'Other service unhealthy'}
            if(($rows|Where-Object Service -eq 'WORKER').Result -eq 'PASS'){$stable++}else{$stable=0}
            if($stable -ge 4){$verified=$true; break}
        }
    } while((Get-Date) -lt $deadline)
    if(-not $verified){throw 'Supervisor did not restore a verified healthy Worker in time; no manual launch attempted'}
    $newLog=@(Get-Content -LiteralPath $log|Select-Object -Skip $logLines)
    $runtime=$newTree.Targets[0]
    if(-not @($newLog|Where-Object {$_ -match "worker [^ ]+-$($runtime.ProcessId) started"}).Count){throw 'New runtime startup log not found'}
    if(@($newLog|Where-Object {$_ -match 'Traceback|\bERROR\b|worker loop error|attempt \d+ failed|retention sweep failed'}).Count){throw 'New Worker log contains errors; inspect log'}
    $dbAfter=Invoke-JiaanNative $docker @('inspect','--format','{{.State.StartedAt}}','ltc_care-db-1')
    if($dbAfter.ExitCode -ne 0 -or ($dbBefore.Output -join '') -cne ($dbAfter.Output -join '')){throw 'DB startup time changed/unavailable'}
    Assert-ProtectedProcesses $protected @(Get-CimInstance Win32_Process)
    if((Get-FileHash $source -Algorithm SHA256).Hash -ne $sourceHash){throw 'Source changed during deployment'}
    $rows|Format-Table -AutoSize
    $newTree.Targets|Select-Object ProcessId,ParentProcessId,ExecutablePath,CreationDate|Format-Table -AutoSize
    Write-Host "PASS: one new Worker group, healthy across four checks; protected processes retained. Source SHA256=$sourceHash"
    Write-Host 'LINE screen and login still require your manual test. No LINE test message was sent.'
} catch {
    Write-Host "STOP: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'No fallback launch, service restart, migration or DB cleanup will be attempted.'
    exit 1
}
