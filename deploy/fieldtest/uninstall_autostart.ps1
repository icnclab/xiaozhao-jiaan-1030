[CmdletBinding(SupportsShouldProcess=$true)]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'status_jiaan.ps1') -Library
$task=Get-ScheduledTask -TaskName 'Jiaan-Autostart' -ErrorAction SilentlyContinue
if(-not $task){Write-Host 'Autostart task absent.'; return}
if($task.Description -ne "Jiaan supervisor: $script:Root"){throw 'Task identity mismatch; refusing removal'}
if($PSCmdlet.ShouldProcess('Jiaan-Autostart','Stop supervisor and unregister startup task')){
    Stop-ScheduledTask -TaskName 'Jiaan-Autostart'
    Unregister-ScheduledTask -TaskName 'Jiaan-Autostart' -Confirm:$false
    Write-Host 'Autostart removed. Logs, DB, models and Funnel configuration retained. Verify service status; use stop_jiaan.ps1 for verified owned app processes.'
}
