[CmdletBinding()]
param([switch]$Restore)
$ErrorActionPreference='Stop'
$source=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$main=Split-Path (Split-Path $source -Parent) -Parent
$work=Join-Path $main 'run\uat-https-pending'
$stateFile=Join-Path $work 'active.json'
$state=Get-Content -LiteralPath $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
$node=Get-CimInstance Win32_Process -Filter "ProcessId=$($state.Tunnel.PID)"
if(-not $node -or $node.ExecutablePath -ine $state.Tunnel.Executable -or $node.CommandLine -notlike '*http://127.0.0.1:18551*' -or [Math]::Abs(($node.CreationDate.ToUniversalTime()-([datetime]$state.Tunnel.Started).ToUniversalTime()).TotalSeconds) -gt 1){throw 'Tunnel identity changed; do not create a replacement tunnel.'}
if(-not $Restore){Write-Output 'CHECK ONLY: restore preparation page on free 18551; existing Tunnel untouched.';return}
if(Get-NetTCPConnection -LocalPort 18551 -State Listen -ErrorAction SilentlyContinue){throw '18551 occupied. Stop only the recorded bridge after identity review; nothing stopped here.'}
$priorPath=Join-Path $work ('active.before-page-restore-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,6)+'.json')
Copy-Item -LiteralPath $stateFile -Destination $priorPath -ErrorAction Stop
$page=Start-Process -FilePath $state.Page.Executable -ArgumentList @('-B',(Join-Path $work 'bootstrap_server.py')) -WorkingDirectory $work -WindowStyle Hidden -PassThru
$node=Get-CimInstance Win32_Process -Filter "ProcessId=$($page.Id)"
if(-not $node -or $node.CommandLine -notlike '*bootstrap_server.py*'){throw 'New preparation page identity not confirmed; inspect without stopping unrelated processes.'}
$state.Page=[pscustomobject]@{PID=$page.Id;Started=$node.CreationDate.ToUniversalTime().ToString('o');Executable=$node.ExecutablePath;Marker='bootstrap_server.py'}
$state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $stateFile -Encoding UTF8
Write-Output 'Preparation page restored; Tunnel and public hostname preserved. Verify /liff is static and /api/config/public returns 404.'
