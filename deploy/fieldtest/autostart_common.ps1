# Shared by the one-shot launcher and the scheduled supervisor (Windows PowerShell 5.1).
function Wait-JiaanReady {
    param([string]$Name,[scriptblock]$Check,[scriptblock]$Repair={},[int]$Attempts=30,[int]$DelaySeconds=10)
    for($attempt=1; $attempt -le $Attempts; $attempt++) {
        try { if(& $Check){ Log-Start "$Name PASS attempt=$attempt/$Attempts"; return } }
        catch { Log-Start "$Name check unavailable attempt=$attempt/$Attempts" }
        Log-Start "$Name WAIT attempt=$attempt/$Attempts retry_in=${DelaySeconds}s"
        try { & $Repair } catch { Log-Start "$Name repair failed; will retry ($($_.Exception.GetType().Name))" }
        if($attempt -lt $Attempts){ Start-Sleep -Seconds $DelaySeconds }
    }
    throw "$Name readiness exhausted ($Attempts attempts); supervisor will retry; no model download or DB replacement"
}
function Start-JiaanDocker {
    # Use the installed CLI with a bounded wait. Do not confuse the helper service with the engine.
    $docker=(Get-Command docker -ErrorAction Stop).Source
    $r=Invoke-JiaanNative $docker @('desktop','start','--detach','--timeout','20')
    if($r.ExitCode -eq 0){return}
    $candidates=@(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'),
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'))
    $desktop=$candidates | Where-Object {Test-Path -LiteralPath $_} | Select-Object -First 1
    if(-not $desktop){throw 'Docker Desktop executable missing'}
    if(-not @(Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue).Count){
        Start-Process -FilePath $desktop -WindowStyle Hidden | Out-Null
    }
}
function Ensure-JiaanTailscale {
    Wait-JiaanReady 'Tailscale' {
        $r=Invoke-JiaanNative $script:Tailscale @('status','--json')
        if($r.ExitCode -ne 0){return $false}
        try { $s=($r.Output -join "`n") | ConvertFrom-Json; $s.BackendState -eq 'Running' -and $s.Self.DNSName.TrimEnd('.') -eq 'stust.tail379935.ts.net' }
        catch {return $false}
    } {
        $svc=Get-Service Tailscale -ErrorAction Stop
        if($svc.Status -ne 'Running'){Start-Service Tailscale}
    } 30 10
    # Retain the node's existing login and network settings. No tailscale up/reset.
    $r=Invoke-JiaanNative $script:Tailscale @('set','--unattended=true')
    if($r.ExitCode -ne 0){throw 'Tailscale unattended configuration failed'}
    Wait-JiaanReady 'Funnel' { Test-JiaanBackgroundFunnel } {
        $r=Invoke-JiaanNative $script:Tailscale @('funnel','--bg','--https=443','http://127.0.0.1:8140')
        if($r.ExitCode -ne 0){throw 'Funnel persistent configuration failed (check existing foreground Funnel)'}
    } 6 10
}
function Test-JiaanBackgroundFunnel {
    $r=Invoke-JiaanNative $script:Tailscale @('funnel','status','--json')
    if($r.ExitCode -ne 0){return $false}
    try {
        $cfg=($r.Output -join "`n") | ConvertFrom-Json
        $site=$cfg.Web.PSObject.Properties['stust.tail379935.ts.net:443']
        $allow=$cfg.AllowFunnel.PSObject.Properties['stust.tail379935.ts.net:443']
        $handler=$site.Value.Handlers.PSObject.Properties['/']
        return $allow.Value -eq $true -and $handler.Value.Proxy.TrimEnd('/') -eq 'http://127.0.0.1:8140'
    } catch {return $false}
}
