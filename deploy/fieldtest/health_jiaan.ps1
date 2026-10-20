[CmdletBinding()]
param([switch]$Json)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'status_jiaan.ps1') -Library
. (Join-Path $PSScriptRoot 'autostart_common.ps1')
try {
    $rows=@(Get-JiaanStatus)
    $rows += [pscustomobject]@{Service='FunnelBackground';Result=$(if(Test-JiaanBackgroundFunnel){'PASS'}else{'FAIL'});Detail='Persistent HTTPS 443 -> 8140'}
    $task=Get-ScheduledTask -TaskName 'Jiaan-Autostart' -ErrorAction SilentlyContinue
    $rows += [pscustomobject]@{Service='Autostart';Result=$(if($task -and $task.State -eq 'Running'){'PASS'}else{'FAIL'});Detail="Task state=$($task.State)"}
    if($Json){$rows|ConvertTo-Json -Depth 5}else{$rows|Format-Table -AutoSize}
    if(@($rows|Where-Object Result -eq 'FAIL').Count){exit 1}; exit 0
} catch {Write-Error 'Health check unavailable; run under the installed administrator account.'; exit 1}
