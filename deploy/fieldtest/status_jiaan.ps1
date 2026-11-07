[CmdletBinding()]
param([switch]$Library)
$ErrorActionPreference = 'Stop'
$script:Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$script:ExpectedRoot = 'C:\aa\ltc_care_installer_20260912\ltc_care'
if ($script:Root -ine $script:ExpectedRoot) { throw 'Refusing to operate outside the aa project.' }
$script:RunDir = Join-Path $PSScriptRoot 'run'
$script:LogDir = Join-Path $PSScriptRoot 'logs'
$script:Tailscale = 'C:\Program Files\Tailscale\tailscale.exe'
$script:BackendPython = Join-Path $script:Root 'backend\.venv\Scripts\python.exe'
$script:AsrPython = Join-Path $script:Root 'venv_asr\Scripts\python.exe'

$script:HttpFailures = @{}
function Invoke-JiaanNative([string]$Executable, [string[]]$Arguments, [int]$TimeoutSeconds=30) {
    # Bound every native call, including docker info during boot. Capture stderr
    # independently: diagnostic text is never interpreted as an exit status.
    $process=New-Object System.Diagnostics.Process
    try {
        $info=New-Object System.Diagnostics.ProcessStartInfo
        $info.FileName=$Executable
        $info.Arguments=($Arguments | ForEach-Object {
            # Windows CommandLineToArgvW quoting, including trailing backslashes.
            '"' + [regex]::Replace([regex]::Replace($_,'(\\*)"','$1$1\"'),'(\\+)$','$1$1') + '"'
        }) -join ' '
        $info.UseShellExecute=$false; $info.CreateNoWindow=$true
        $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true
        $info.StandardOutputEncoding=[Text.Encoding]::UTF8; $info.StandardErrorEncoding=[Text.Encoding]::UTF8
        $process.StartInfo=$info
        if(-not $process.Start()){throw 'Native start failed'}
        $stdout=$process.StandardOutput.ReadToEndAsync(); $stderr=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit($TimeoutSeconds*1000)){
            $process.Kill(); $process.WaitForExit()
            return [pscustomobject]@{ExitCode=124;Output=@('Native command timeout')}
        }
        $output=@(($stdout.Result + "`n" + $stderr.Result) -split "`r?`n" | Where-Object {$_})
        return [pscustomobject]@{ExitCode=$process.ExitCode;Output=$output}
    } catch { return [pscustomobject]@{ExitCode=-1;Output=@()} }
    finally {$process.Dispose()}
}
function Get-HttpJson([string]$Url) {
    try {
        $result = Invoke-RestMethod -Uri $Url -TimeoutSec 5
        $script:HttpFailures.Remove($Url)
        return $result
    } catch {
        $reason = if ($_.Exception.Response) { 'HTTP ' + [int]$_.Exception.Response.StatusCode }
                  elseif ($_.Exception.Status) { [string]$_.Exception.Status }
                  else { $_.Exception.GetType().Name }
        $script:HttpFailures[$Url] = $reason
        return $null
    }
}
function Get-PortOwner([int]$Port) {
    @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}
function Get-AaProcesses([string]$Kind) {
    $pattern = switch ($Kind) { 'api' { '\buvicorn\s+app\.main:app\b' }; 'worker' { '-m\s+app\.worker\b' }; 'stt' { 'services[\\/]stt_sidecar[\\/]server\.py' } }
    $exe = if ($Kind -eq 'stt') { $script:AsrPython } else { $script:BackendPython }
    $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    # An unreadable Python command line cannot safely be dismissed as unrelated.
    if (@($all | Where-Object { $_.Name -eq 'python.exe' -and (-not $_.CommandLine -or -not $_.ExecutablePath) }).Count) {
        throw 'Python identity unavailable; use administrator PowerShell. No duplicate launch permitted.'
    }
    @($all | Where-Object { $_.ExecutablePath -ieq $exe -and $_.CommandLine -match $pattern })
}
function Test-AaPort([int]$Port, $Processes) {
    $listeners = @(Get-PortOwner $Port)
    if (-not $listeners.Count -or @($Processes).Count -ne 1) { return $false }
    $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    foreach ($listener in $listeners) {
        $cursor = [int]$listener.OwningProcess; $seen = @{}
        while ($cursor -and -not $seen.ContainsKey($cursor)) {
            if ($cursor -eq $Processes[0].ProcessId) { break }
            $seen[$cursor] = $true
            $node = $all | Where-Object ProcessId -eq $cursor | Select-Object -First 1
            if (-not $node -or $node.Name -ne 'python.exe') { return $false }
            $cursor = [int]$node.ParentProcessId
        }
        if ($cursor -ne $Processes[0].ProcessId) { return $false }
    }
    return $true
}
function Test-Funnel {
    if (-not (Test-Path -LiteralPath $script:Tailscale)) { return $false }
    $native = Invoke-JiaanNative $script:Tailscale @('funnel','status','--json')
    if ($native.ExitCode -ne 0) { return $false }
    $raw = $native.Output
    try { $config = ($raw -join "`n") | ConvertFrom-Json } catch { return $false }
    $configs = @($config)
    if ($config.Foreground) { $configs += @($config.Foreground.PSObject.Properties | ForEach-Object Value) }
    foreach ($cfg in $configs) {
        if (-not $cfg.Web -or -not $cfg.AllowFunnel) { continue }
        foreach ($site in $cfg.Web.PSObject.Properties) {
            $allow = $cfg.AllowFunnel.PSObject.Properties[$site.Name]
            $handler = $site.Value.Handlers.PSObject.Properties['/']
            if ($site.Name -eq 'stust.tail379935.ts.net:443' -and $allow -and $allow.Value -eq $true -and
                $handler -and $handler.Value.Proxy.TrimEnd('/') -eq 'http://127.0.0.1:8140') { return $true }
        }
    }
    return $false
}
function Get-JiaanStatus {
    $rows = @()
    $dockerOk = $false; $dbOk = $false
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        $native = Invoke-JiaanNative (Get-Command docker).Source @('info','--format','{{.ServerVersion}}')
        $dockerOk = $native.ExitCode -eq 0
        if ($dockerOk) {
            $native = Invoke-JiaanNative (Get-Command docker).Source @('inspect','ltc_care-db-1')
            $raw = $native.Output
            if ($native.ExitCode -eq 0) {
                $db = @(($raw -join "`n") | ConvertFrom-Json)[0]
                $dbOk = $db.Config.Labels.'com.docker.compose.project' -eq 'ltc_care' -and
                    $db.Config.Labels.'com.docker.compose.service' -eq 'db' -and
                    @($db.Mounts | Where-Object {$_.Name -eq 'ltc_care_ltc_pgdata' -and $_.Destination -eq '/var/lib/postgresql/data'}).Count -eq 1 -and
                    $db.State.Running -and $db.State.Health.Status -eq 'healthy'
            }
        }
    }
    $rows += [pscustomobject]@{Service='Docker';Result=$(if($dockerOk){'PASS'}else{'FAIL'});Detail='Docker engine'}
    $rows += [pscustomobject]@{Service='DB';Result=$(if($dbOk){'PASS'}else{'FAIL'});Detail='aa: ltc_care-db-1 / 55432'}
    $ollama = Get-HttpJson 'http://127.0.0.1:11434/api/tags'
    $modelOk = $ollama -and @($ollama.models | Where-Object name -eq 'gemma4:e4b').Count -gt 0
    $rows += [pscustomobject]@{Service='Ollama';Result=$(if($ollama){'PASS'}else{'FAIL'});Detail='127.0.0.1:11434'}
    $rows += [pscustomobject]@{Service='Model';Result=$(if($modelOk){'PASS'}else{'FAIL'});Detail='gemma4:e4b available (not an inference test)'}
    $stt = Get-HttpJson 'http://127.0.0.1:8147/healthz'
    $api = Get-HttpJson 'http://127.0.0.1:8140/api/healthz'
    foreach ($kind in 'stt','api','worker') {
        try { $p = @(Get-AaProcesses $kind); $identity = $true } catch { $p = @(); $identity = $false }
        $port = if($kind -eq 'stt'){8147}elseif($kind -eq 'api'){8140}else{0}
        $ok = $identity -and $p.Count -eq 1
        $detail = "aa process count=$($p.Count)"
        if ($port) {
            $detail += "; port=$port listening=$(@(Get-PortOwner $port).Count -gt 0)"
            try { $ok = $ok -and (Test-AaPort $port $p) } catch { $ok = $false }
        }
        if ($kind -eq 'stt') { $ok = $ok -and $stt.ok -and $stt.model -eq 'medium' -and $stt.device -eq 'cuda' -and 'medium' -in $stt.loaded }
        if ($kind -eq 'api') {
            $ok = $ok -and $api.db -eq 'ok' -and $api.modes.line -eq 'real'
            if (-not $api) { $detail += '; healthz query failed: ' + $script:HttpFailures['http://127.0.0.1:8140/api/healthz'] }
        }
        if ($kind -eq 'worker') {
            $age = $api.worker_heartbeat_age_sec
            $ok = $ok -and $null -ne $age -and $age -ge 0 -and $age -lt 60
            if (-not $api) {
                $detail += '; heartbeat=N/A (API healthz unavailable: ' + $script:HttpFailures['http://127.0.0.1:8140/api/healthz'] + '); process existence does not prove heartbeat health'
            } elseif ($null -eq $age) {
                $detail += '; heartbeat=N/A (API returned no heartbeat record)'
            } else { $detail += "; heartbeat seconds=$age" }
        }
        $rows += [pscustomobject]@{Service=$kind.ToUpper();Result=$(if($ok){'PASS'}else{'FAIL'});Detail=$detail}
    }
    $funnelOk = Test-Funnel
    $rows += [pscustomobject]@{Service='Funnel';Result=$(if($funnelOk){'PASS'}else{'FAIL'});Detail=$(if($funnelOk){'HTTPS 443 -> aa 8140; external reachability needs phone test'}else{'Funnel unavailable; autostart retries persistent --bg configuration'})}
    return $rows
}
function Get-LaunchSpec([string]$Kind) {
    $exe = if($Kind -eq 'stt'){$script:AsrPython}else{$script:BackendPython}
    $cwd = if($Kind -eq 'stt'){$script:Root}else{Join-Path $script:Root 'backend'}
    $args = switch($Kind) {
        'api' { @('-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8140') }
        'worker' { @('-B','-m','app.worker') }
        'stt' { @('-B',(Join-Path $script:Root 'services\stt_sidecar\server.py'),'--host','127.0.0.1','--port','8147','--model','medium','--device','cuda') }
        default { throw 'Unknown service' }
    }
    function Quote-PS([string]$s) { "'" + $s.Replace("'","''") + "'" }
    $log = Join-Path $script:LogDir "$Kind.log"
    $command = '$ErrorActionPreference=''Continue''; $env:PYTHONUTF8=''1''; $env:PYTHONIOENCODING=''utf-8''; ' +
        'Set-Location -LiteralPath ' + (Quote-PS $cwd) + '; & ' + (Quote-PS $exe) + ' ' +
        (($args | ForEach-Object { Quote-PS $_ }) -join ' ') + ' *>> ' + (Quote-PS $log) + '; exit $LASTEXITCODE'
    if($Kind -in @('api','worker')){ $command = '. ' + (Quote-PS (Join-Path $PSScriptRoot 'load_webpush_runtime.ps1')) + '; ' + $command }
    [pscustomobject]@{Encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command));Exe=$exe;Kind=$Kind}
}
if (-not $Library) {
    try { $rows = @(Get-JiaanStatus); $rows | Format-Table -AutoSize; if (@($rows | Where-Object Result -eq 'FAIL').Count) { exit 1 }; exit 0 }
    catch { Write-Host 'FAIL: health check could not complete; check permissions and dependencies.'; exit 1 }
}

