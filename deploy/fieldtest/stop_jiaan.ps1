[CmdletBinding(SupportsShouldProcess=$true)]
param([ValidateSet('api','worker','stt')][string[]]$Services=@('api','worker','stt'))
$ErrorActionPreference='Stop'
function Get-VerifiedWorkerTree($All,$Record,$Spec,[string]$Root,[string]$BasePython) {
    if($Record.Project -ine $Root -or $Record.Kind -ne 'worker' -or $Record.Encoded -cne $Spec.Encoded){throw 'Ownership record mismatch'}
    $owner=@($All|Where-Object ProcessId -eq $Record.PID)
    $wrapper="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    if($owner.Count -ne 1 -or $owner[0].ExecutablePath -ine $wrapper -or
       $owner[0].Name -ine 'powershell.exe' -or $owner[0].CommandLine -notlike "* $($Spec.Encoded)*" -or
       [math]::Abs(($owner[0].CreationDate.ToUniversalTime()-([datetime]$Record.Started).ToUniversalTime()).TotalMilliseconds) -gt 1){throw 'Wrapper identity unavailable or changed'}
    if(@($All|Where-Object {$_.Name -ieq 'python.exe' -and (-not $_.ExecutablePath -or -not $_.CommandLine -or -not $_.CreationDate)}).Count){throw 'Python identity unavailable'}
    $launchers=@($All|Where-Object {$_.ExecutablePath -ieq $Spec.Exe -and $_.CommandLine -match '-m\s+app\.worker\b'})
    if($launchers.Count -ne 1 -or $launchers[0].ParentProcessId -ne $Record.PID){throw 'Multiple/missing Worker or wrong parent'}
    $launcher=$launchers[0]
    $pattern='^\s*(?:"'+[regex]::Escape($Spec.Exe)+'"|"'+[regex]::Escape($BasePython)+'"|'+[regex]::Escape($Spec.Exe)+'|'+[regex]::Escape($BasePython)+')\s+-B\s+-m\s+app\.worker\s*$'
    $children=@(); $parents=@([int]$Record.PID); $seen=@{}; $seen[[int]$Record.PID]=$true
    do {
        $next=@($All|Where-Object {$_.ParentProcessId -in $parents})
        foreach($node in $next){if($seen.ContainsKey([int]$node.ProcessId)){throw 'Cyclic process tree'}; $seen[[int]$node.ProcessId]=$true}
        $children += $next; $parents=@($next|ForEach-Object {[int]$_.ProcessId})
    } while($parents.Count)
    $baseCount=0; $consoleCount=0
    foreach($node in $children){
        $parent=@($All|Where-Object ProcessId -eq $node.ParentProcessId)
        if(-not $node.ExecutablePath -or -not $node.CommandLine -or -not $node.CreationDate -or $parent.Count -ne 1 -or $node.CreationDate -lt $parent[0].CreationDate){throw 'Descendant identity/time unavailable or changed'}
        if($node.Name -ieq 'conhost.exe'){
            if($node.ExecutablePath -ine "$env:SystemRoot\System32\conhost.exe" -or $node.ParentProcessId -ne $Record.PID -or @($All|Where-Object ParentProcessId -eq $node.ProcessId).Count){throw 'Unexpected console identity/parent/children'}
            $consoleCount++; continue
        }
        if($node.Name -ine 'python.exe' -or $node.CommandLine -notmatch $pattern){throw 'Unexpected descendant; refusing entire stop'}
        if($node.ProcessId -eq $launcher.ProcessId){
            if($node.ExecutablePath -ine $Spec.Exe){throw 'Wrong launcher path'}
        } elseif($node.ExecutablePath -ieq $BasePython -and $node.ParentProcessId -eq $launcher.ProcessId){$baseCount++}
        else {throw 'Unexpected Python path/parent'}
    }
    if($baseCount -ne 1 -or $consoleCount -gt 1){throw 'Unexpected Python/console count'}
    # conhost is validated, but never included in stop targets. Leaf Python first.
    [pscustomobject]@{Targets=@($children|Where-Object {$_.Name -ieq 'python.exe' -and $_.ProcessId -ne $launcher.ProcessId})+@($launcher)+@($owner[0]); Members=@($owner[0])+@($children)}
}
function Get-WorkerTreeStamp($Tree) {
    ($Tree.Members|Sort-Object ProcessId|ForEach-Object {
        '{0}|{1}|{2}|{3}|{4:o}' -f $_.ProcessId,$_.ParentProcessId,$_.ExecutablePath,$_.CommandLine,$_.CreationDate
    }) -join "`n"
}
. (Join-Path $PSScriptRoot 'status_jiaan.ps1') -Library
if(-not (Test-Path -LiteralPath $script:RunDir)){Write-Host 'No owned processes recorded.'; exit 0}
$lock=$null; $failed=$false
try {
    $lock=[IO.File]::Open((Join-Path $script:RunDir 'launcher.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    foreach($kind in $Services) {
        $file=Join-Path $script:RunDir "$kind.json"
        if(-not (Test-Path -LiteralPath $file)){continue}
        try {
            $record=Get-Content -LiteralPath $file -Raw|ConvertFrom-Json
            $spec=Get-LaunchSpec $kind
            if($record.Project -ine $script:Root -or $record.Kind -ne $kind -or $record.Encoded -cne $spec.Encoded){throw 'Ownership record mismatch'}
            $all=@(Get-CimInstance Win32_Process)
            if($kind -eq 'worker'){
                $cfg=Get-Content -LiteralPath (Join-Path $script:Root 'backend\.venv\pyvenv.cfg')
                $baseLines=@($cfg|Where-Object {$_ -match '^executable\s*='})
                if($baseLines.Count -ne 1){throw 'Base Python configuration unavailable'}
                $basePython=($baseLines[0] -split '=',2)[1].Trim()
                if(-not [IO.Path]::IsPathRooted($basePython) -or -not (Test-Path -LiteralPath $basePython -PathType Leaf)){throw 'Base Python path unavailable'}
                $tree=Get-VerifiedWorkerTree $all $record $spec $script:Root $basePython
                $stamp=Get-WorkerTreeStamp $tree
                # Open and pin every stop target before stopping any of them.
                $pinned=@()
                try {
                    foreach($target in $tree.Targets){
                        $live=Get-Process -Id $target.ProcessId -ErrorAction Stop
                        $pinned += $live
                        $null=$live.Handle
                        if([math]::Abs(($live.StartTime.ToUniversalTime()-$target.CreationDate.ToUniversalTime()).TotalMilliseconds) -gt 1){throw 'Process identity changed'}
                    }
                    $fresh=Get-VerifiedWorkerTree @(Get-CimInstance Win32_Process) $record $spec $script:Root $basePython
                    if((Get-WorkerTreeStamp $fresh) -cne $stamp){throw 'Process tree changed; refusing stop'}
                    if($PSCmdlet.ShouldProcess('aa fieldtest worker','Stop verified Python Worker and wrapper; retain conhost')){
                        # Recheck after a possible confirmation prompt.
                        $fresh=Get-VerifiedWorkerTree @(Get-CimInstance Win32_Process) $record $spec $script:Root $basePython
                        if((Get-WorkerTreeStamp $fresh) -cne $stamp){throw 'Process tree changed; refusing stop'}
                        foreach($live in $pinned){if($live.HasExited){throw 'Process exited before stop'}}
                        foreach($live in $pinned){Stop-Process -InputObject $live -ErrorAction Stop}
                        Remove-Item -LiteralPath $file
                        Write-Host 'worker stopped (verified Python/wrapper only; conhost retained)'
                    }
                } finally {foreach($live in $pinned){$live.Dispose()}}
                continue
            }
            $owner=$all|Where-Object ProcessId -eq $record.PID|Select-Object -First 1
            if(-not $owner){Write-Host "$kind wrapper absent; refusing to stop any orphan or other process"; $failed=$true; continue}
            $expectedExe="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
            if($owner.ExecutablePath -ine $expectedExe -or $owner.CommandLine -notlike "* $($spec.Encoded)*" -or
                [math]::Abs(($owner.CreationDate.ToUniversalTime()-([datetime]$record.Started).ToUniversalTime()).TotalMilliseconds) -gt 1){throw 'PID/start time/command line mismatch'}
            $children=@(); $parents=@([int]$owner.ProcessId)
            do {
                $next=@($all|Where-Object { $_.ParentProcessId -in $parents })
                $children += $next; $parents=@($next|ForEach-Object {[int]$_.ProcessId})
            } while($parents.Count)
            foreach($child in $children){
                $isPython=$child.Name -eq 'python.exe' -and $child.CommandLine -and
                    ($child.CommandLine -match [regex]::Escape($spec.Exe) -or
                     ($child.ExecutablePath -and $child.CommandLine -match $(switch($kind){'api'{'uvicorn\s+app\.main:app'};'worker'{'-m\s+app\.worker\b'};'stt'{'services[\\/]stt_sidecar[\\/]server\.py'}})))
                if(-not $isPython){throw 'Unexpected descendant; refusing entire stop'}
            }
            if($PSCmdlet.ShouldProcess("aa fieldtest $kind",'Stop verified owned process tree')){
                # Get-Process objects pin the checked identity; never kill by port/name.
                $targets=@($children)+@($owner)
                foreach($target in $targets){
                    $live=Get-Process -Id $target.ProcessId -ErrorAction Stop
                    if([math]::Abs(($live.StartTime.ToUniversalTime()-$target.CreationDate.ToUniversalTime()).TotalMilliseconds) -gt 1){throw 'Process identity changed; refusing stop'}
                    Stop-Process -InputObject $live -ErrorAction Stop
                }
                Remove-Item -LiteralPath $file
                Write-Host "$kind stopped (owned by fieldtest only)"
            }
        } catch {Write-Host "REFUSED $kind : $($_.Exception.Message)"; $failed=$true}
    }
} catch {Write-Host 'REFUSED: launcher lock or process inventory unavailable'; $failed=$true}
finally {if($lock){$lock.Dispose()}}
if($failed){exit 1}; exit 0
