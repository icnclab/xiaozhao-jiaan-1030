[CmdletBinding()]
param([ValidateSet('api','worker','bridge')][string]$Kind='api',[switch]$Launch)
$ErrorActionPreference='Stop'
$source=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$main=Split-Path (Split-Path $source -Parent) -Parent
$py=Join-Path $main 'backend\.venv\Scripts\python.exe'
$envFile=Join-Path $main 'run\uat-private\uat.local.env'
$checker=Join-Path $source 'backend\scripts\check_uat_cutover.py'
& $py -B $checker --env-file $envFile
if($LASTEXITCODE -ne 0){throw 'Offline UAT readiness failed; nothing started.'}
if(-not $Launch){Write-Output 'CHECK ONLY: no process stopped or started. -Launch requires separate cutover authorization.';return}
$prep=Get-Content -LiteralPath (Join-Path $main 'run\uat-https-pending\cutover-prep-latest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$prior=Get-Content -LiteralPath (Join-Path $prep.folder 'demo-processes.private.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach($record in @($prior.worker | Where-Object {$_.ApplicationStopCandidate})){
    $old=Get-CimInstance Win32_Process -Filter "ProcessId=$($record.PID)"
    if($old -and [Math]::Abs(($old.CreationDate.ToUniversalTime()-[datetime]$record.CreatedUtc).TotalSeconds) -lt 1){throw 'Original demo Worker still running; no UAT process started.'}
}
if($Kind -eq 'bridge'){
    & $py -B $checker --env-file $envFile --live
    if($LASTEXITCODE -ne 0){throw 'UAT live readiness failed; bridge not started.'}
    if(Get-NetTCPConnection -LocalPort 18551 -State Listen -ErrorAction SilentlyContinue){throw '18551 occupied; nothing stopped.'}
    $argsUat=@('-B',(Join-Path $PSScriptRoot 'https_bridge.py'),'--active-file',(Join-Path $main 'run\uat-https-pending\active.json'),'--launch')
} else {
    $argsUat=@('-B',(Join-Path $source 'backend\scripts\run_uat.py'),'--env-file',$envFile,'--kind',$Kind,'--launch')
}
$stamp=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,6)
$privateRun=Join-Path $main ('run\uat-private\launch-'+$stamp)
New-Item -ItemType Directory -Path $privateRun | Out-Null
# Child inherits dedicated profile selection; do not mutate the caller's settings.
$savedProfile=$env:LTC_PROFILE;$savedFile=$env:LTC_UAT_ENV_FILE
try{
    $env:LTC_PROFILE='uat';$env:LTC_UAT_ENV_FILE=$envFile
    $proc=Start-Process -FilePath $py -ArgumentList $argsUat -WorkingDirectory (Join-Path $source 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $privateRun 'out.log') -RedirectStandardError (Join-Path $privateRun 'err.log')
} finally {$env:LTC_PROFILE=$savedProfile;$env:LTC_UAT_ENV_FILE=$savedFile}
$node=Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)"
[ordered]@{Kind=$Kind;RootPID=$proc.Id;CreatedUtc=$node.CreationDate.ToUniversalTime().ToString('o');Executable=$node.ExecutablePath;Source=$source;Stopped=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $privateRun 'process.json') -Encoding UTF8
Write-Output "Started requested UAT child only; verify its descendants/listener and private log: $privateRun"
