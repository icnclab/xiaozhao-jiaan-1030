[CmdletBinding()]
param([switch]$Once)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'status_jiaan.ps1') -Library
. (Join-Path $PSScriptRoot 'autostart_common.ps1')
New-Item -ItemType Directory -Force $script:RunDir,$script:LogDir | Out-Null
function Log-Start([string]$Message) {
    $path=Join-Path $script:LogDir 'autostart.log'
    if((Test-Path $path) -and (Get-Item $path).Length -gt 10MB){Move-Item -LiteralPath $path -Destination ($path+'.1') -Force}
    Add-Content -LiteralPath $path -Encoding UTF8 -Value "$(Get-Date -Format o) $Message"
}
$lock=$null
$ps="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
function Invoke-ManagedScript([string]$Name,[string[]]$Extra=@()) {
    $r=Invoke-JiaanNative $ps (@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot $Name))+$Extra) 7200
    return $r.ExitCode
}
try {
    try {$lock=[IO.File]::Open((Join-Path $script:RunDir 'supervisor.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}
    catch {exit 0} # Another supervisor already owns this project.
    Log-Start "Supervisor started; account=$([Security.Principal.WindowsIdentity]::GetCurrent().Name)"
    $failures=@{}; $cycle=0; $lastSummary=''
    do {
        $cycle++
        try {
            $rows=@(Get-JiaanStatus)
            $bad=@($rows | Where-Object Result -eq 'FAIL')
            if($cycle -eq 1 -or $bad.Count -or -not (Test-JiaanBackgroundFunnel)){
                Log-Start "Repair cycle=$cycle failed=$($bad.Service -join ',')"
                # Allow three failed observations before restarting a verified owned process.
                # A stale worker heartbeat with a broken API/DB is not proof the worker is broken.
                foreach($kind in 'stt','api','worker'){
                    $row=$rows|Where-Object Service -eq $kind.ToUpper()
                    if($row.Result -eq 'FAIL'){$failures[$kind]=1+[int]$failures[$kind]}else{$failures[$kind]=0}
                    $depsOk=@($rows|Where-Object {$_.Service -in @('DB','Docker','Ollama','Model') -and $_.Result -eq 'FAIL'}).Count -eq 0
                    if($kind -eq 'worker'){$depsOk=$depsOk -and ($rows|Where-Object Service -eq 'API').Result -eq 'PASS'}
                    if($failures[$kind] -ge 3 -and $depsOk -and @(Get-AaProcesses $kind).Count){
                        $code=Invoke-ManagedScript 'stop_jiaan.ps1' @('-Services',$kind)
                        Log-Start "$kind owned restart stop_exit=$code (unowned processes are retained)"
                        $failures[$kind]=0
                    }
                }
                $code=Invoke-ManagedScript 'start_jiaan.ps1' @('-AutoStart')
                Log-Start "Startup cycle=$cycle exit=$code; next health check in 30s"
            }
            $rows=@(Get-JiaanStatus)
            $snapshot=[ordered]@{CheckedAt=(Get-Date -Format o);Services=$rows;FunnelBackground=(Test-JiaanBackgroundFunnel)}
            $temp=Join-Path $script:RunDir 'health.tmp.json'
            $snapshot|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $temp -Encoding UTF8
            Move-Item -LiteralPath $temp -Destination (Join-Path $script:RunDir 'health.json') -Force
            $summary=($rows|ForEach-Object {"$($_.Service)=$($_.Result)"}) -join ' '
            if($summary -ne $lastSummary -or $cycle % 20 -eq 0){Log-Start $summary; $lastSummary=$summary}
        } catch {Log-Start "Cycle=$cycle error=$($_.Exception.GetType().Name); retry in 30s"}
        if($Once){break}
        Start-Sleep -Seconds 30
    } while($true)
    if(@($rows|Where-Object Result -eq 'FAIL').Count -or -not (Test-JiaanBackgroundFunnel)){exit 1}
} finally {if($lock){$lock.Dispose()}}
