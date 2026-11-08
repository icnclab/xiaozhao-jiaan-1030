# Windows only. Creates a repeating 15-minute task under the current user.
# Run after verifying the lab Google Drive identity and the local config.
# Avoid admin elevation; no changes to production services/databases.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$PythonExe,
    [Parameter(Mandatory=$true)][string]$ConfigFile,
    [string]$TaskName='XiaoZhao-ApprovedDualBackup-15min',
    [int]$Minutes=15,
    [switch]$Install
)
$ErrorActionPreference='Stop'
if ($Minutes -lt 5 -or $Minutes -gt 1440) { throw 'Minutes must be 5..1440' }
foreach ($p in @($PythonExe,$ConfigFile)) { if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Missing file: $p" } }
$ScriptPath = Join-Path $PSScriptRoot 'sync_verified.py'
if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) { throw 'Missing sync_verified.py' }
$Arguments='"{0}" --config "{1}"' -f $ScriptPath,$ConfigFile
Write-Host "TaskName: $TaskName"
Write-Host "Python: $PythonExe"
Write-Host "Script: $ScriptPath"
Write-Host "Config: $ConfigFile"
Write-Host "Interval: $Minutes minutes"
if (-not $Install) {
    Write-Host 'DRY RUN ONLY. Add -Install after account / Drive folder verification.'
    exit 0
}
$Cfg=Get-Content -LiteralPath $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Cfg.driveMode -ne 'api' -or -not $Cfg.driveEnabled -or -not $Cfg.driveAccountCheckedByHuman) { throw 'Drive API OAuth/account/folder/cloud checks must be complete; schedule remains disabled.' }
$Equivalent=@(Get-ScheduledTask | Where-Object { @($_.Actions | Where-Object { $_.Arguments -like '*sync_verified.py*' }).Count -gt 0 })
if($Equivalent.Count){ throw 'Equivalent sync schedule exists; do not create a competing task.' }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { throw "Task exists: $TaskName; will not overwrite" }
$CurrentUser=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$Act=New-ScheduledTaskAction -Execute $PythonExe -Argument $Arguments -WorkingDirectory (Split-Path $ScriptPath -Parent)
$StartAt=(Get-Date).AddMinutes(2)
$Trig=New-ScheduledTaskTrigger -Once -At $StartAt -RepetitionInterval (New-TimeSpan -Minutes $Minutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$Principal=New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel LeastPrivilege
$Settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 25) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $Act -Trigger $Trig -Principal $Principal -Settings $Settings | Out-Null
Write-Host 'Scheduled task created. It can only run while this user is logged on. Check task history and Drive cloud status.'
