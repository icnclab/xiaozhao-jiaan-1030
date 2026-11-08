[CmdletBinding()]
param([switch]$StopPage)
$ErrorActionPreference='Stop'
$source=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$main=Split-Path (Split-Path $source -Parent) -Parent
$state=Get-Content -LiteralPath (Join-Path $main 'run\uat-https-pending\active.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$page=$state.Page;$tunnel=$state.Tunnel
foreach($record in @($page,$tunnel)){
    $node=Get-CimInstance Win32_Process -Filter "ProcessId=$($record.PID)"
    if(-not $node -or $node.ExecutablePath -ine $record.Executable -or $node.CommandLine -notlike "*$($record.Marker)*" -or [Math]::Abs(($node.CreationDate.ToUniversalTime()-([datetime]$record.Started).ToUniversalTime()).TotalSeconds) -gt 1){throw 'Recorded identity changed; no process stopped.'}
}
if($page.Marker -ne 'bootstrap_server.py' -or $tunnel.Marker -ne 'http://127.0.0.1:18551'){throw 'Unexpected scope; nothing stopped.'}
$listener=@(Get-NetTCPConnection -LocalPort 18551 -State Listen)
if($listener.Count -ne 1 -or $listener[0].OwningProcess -ne $page.PID -or $listener[0].LocalAddress -ne '127.0.0.1'){throw 'Preparation listener changed.'}
if(-not $StopPage){Write-Output 'CHECK ONLY: only the recorded preparation page would stop; Tunnel remains running.';return}
Stop-Process -Id $page.PID -ErrorAction Stop
Write-Output 'Stopped only recorded preparation page. Tunnel preserved; start the approved bridge or restore page immediately.'
