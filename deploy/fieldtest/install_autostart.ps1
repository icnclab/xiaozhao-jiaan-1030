[CmdletBinding()]
param([switch]$NoStart)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'status_jiaan.ps1') -Library
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$targetUser='stust\icncl'
$targetAccount=New-Object Security.Principal.NTAccount($targetUser)
if($targetAccount.Translate([Security.Principal.SecurityIdentifier]).Value -ne $identity.User.Value){
    throw 'Run this installer as stust\icncl, the existing Docker/Ollama account.'
}
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
    throw 'Run this installer from an administrator PowerShell under the existing Docker/Ollama account.'
}
foreach($p in $script:BackendPython,$script:AsrPython,$script:Tailscale,(Join-Path $PSScriptRoot 'autostart_jiaan.ps1')){
    if(-not(Test-Path -LiteralPath $p -PathType Leaf)){throw "Required file missing: $p"}
}
foreach($tool in 'docker','ollama'){Get-Command $tool -ErrorAction Stop | Out-Null}
# Interactive uses the user's existing logon token, including a PIN logon.
# No credential prompt, Password/S4U logon, or stored account secret.
New-Item -ItemType Directory -Force $script:RunDir,$script:LogDir | Out-Null
$taskName='Jiaan-Autostart'
$existing=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if($existing){
    if($existing.Description -ne "Jiaan supervisor: $script:Root"){throw 'Task name belongs to another deployment; refusing overwrite'}
}
$ps="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$actionArguments='-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+(Join-Path $PSScriptRoot 'autostart_jiaan.ps1')+'"'
$action=New-ScheduledTaskAction -Execute $ps -Argument $actionArguments -WorkingDirectory $script:Root
$logon=New-ScheduledTaskTrigger -AtLogOn -User $targetUser
$logon.Delay='PT30S'
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$taskPrincipal=New-ScheduledTaskPrincipal -UserId $targetUser -LogonType Interactive -RunLevel Highest
$task=New-ScheduledTask -Action $action -Trigger $logon -Settings $settings -Principal $taskPrincipal -Description "Jiaan supervisor: $script:Root"
# Remove the previous task registration, including any stored Password-logon
# credential, before recreating this one name with an InteractiveToken principal.
if($existing){
    Stop-ScheduledTask -TaskName $taskName
    # Stop-ScheduledTask may return before the old supervisor releases its lock.
    # Do not let the new task exit successfully just because the old one is stopping.
    $lockPath=Join-Path $script:RunDir 'supervisor.lock'
    $released=$false
    for($attempt=1; $attempt -le 30; $attempt++){
        if(-not(Test-Path -LiteralPath $lockPath)){$released=$true; break}
        $probe=$null
        try {
            $probe=[IO.File]::Open($lockPath,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
            $released=$true
        } catch {} finally {if($probe){$probe.Dispose()}}
        if($released){break}
        Start-Sleep -Seconds 1
    }
    if(-not $released){throw 'Old supervisor is still stopping; rerun installer after it releases its lock.'}
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
Add-Content -LiteralPath (Join-Path $script:LogDir 'install.log') -Encoding UTF8 -Value "$(Get-Date -Format o) Registered $taskName user=$targetUser logon/interactive/no-password/hidden"
if(-not $NoStart){Start-ScheduledTask -TaskName $taskName}
Write-Host 'Installed Jiaan-Autostart for stust\icncl. Run only when user is logged on; no Windows password required or stored.'
Write-Host 'Logon delay: 30s; health check: 30s; supervisor failure restart: 1 minute. PIN login is supported.'
Write-Host 'Check health_jiaan.ps1 and logs\autostart.log. Reboot and sign in to test the actual logon trigger.'
