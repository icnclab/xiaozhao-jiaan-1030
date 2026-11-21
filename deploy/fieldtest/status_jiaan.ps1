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
            # Only quote args containing whitespace/quotes. wsl.exe does its own
            # command-line re-parsing and mishandles short flags (-d, --) when every
            # argument is unconditionally quoted (seen as exit=127 "-d: command not found").
            if($_ -match '[\s"]') {
                '"' + [regex]::Replace([regex]::Replace($_,'(\\*)"','$1$1\"'),'(\\+)$','$1$1') + '"'
            } else { $_ }
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
function Get-HttpJson([string]$Url, [hashtable]$Headers) {
    try {
        $result = if ($Headers) { Invoke-RestMethod -Uri $Url -TimeoutSec 5 -Headers $Headers }
                  else { Invoke-RestMethod -Uri $Url -TimeoutSec 5 }
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
# /api/healthz 對公開網路（Tailscale Funnel）只回傳精簡版（status／worker 心跳）；
# 本機既有腳本要繼續拿到 database_name、provider 模式，帶這個只存在本機、
# 已被 .gitignore 排除的 Token 當 X-Internal-Health-Token。第一次呼叫前，API
# process 要先啟動過一次才會在這裡生出 Token 檔案；啟動之前這個函式回空字串，
# 呼叫端一樣會拿到（安全的）精簡版，不是硬性失敗。
$script:InternalHealthTokenFile = Join-Path $script:RunDir 'internal_health_token.txt'
function Get-InternalHealthHeaders() {
    if (Test-Path -LiteralPath $script:InternalHealthTokenFile) {
        $token = (Get-Content -LiteralPath $script:InternalHealthTokenFile -Raw).Trim()
        if ($token) { return @{ 'X-Internal-Health-Token' = $token } }
    }
    return $null
}
function Get-PortOwner([int]$Port) {
    @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}
function Get-AaProcesses([string]$Kind) {
    # Port-anchored: this machine runs several app.main:app instances on different ports
    # (8140 LINE/API, 8165 SOS, 8166 SOS45, and others); an unanchored pattern here falsely
    # matches another port's process and makes Start-Owned('api') skip launching a real 8140.
    $pattern = switch ($Kind) {
        'api' { '\buvicorn\s+app\.main:app\b.*--port\s+8140\b' }
        'worker' { '-m\s+app\.worker\b' }
        'stt' { 'services[\\/]stt_sidecar[\\/]server\.py' }
        'sos' { '\buvicorn\s+app\.main:app\b.*--port\s+8165\b' }
        'sos45' { '\buvicorn\s+sos45_isolated_api:app\b.*--port\s+8166\b' }
    }
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
                $handler -and $handler.Value.Proxy.TrimEnd('/') -eq 'http://127.0.0.1:29140') { return $true }
        }
    }
    return $false
}
function Get-SosStartDecision([string]$Kind) {
    # Pure decision function for SOS(8165)/SOS45(8166) autostart: never starts or stops
    # anything itself, only says what start_jiaan.ps1 should do. Kept separate from the
    # actual Start-Owned call so the safety-critical occupant/identity logic is testable
    # by overriding Get-PortOwner/Get-AaProcesses/Test-AaPort in a test session.
    $port = if ($Kind -eq 'sos') { 8165 } elseif ($Kind -eq 'sos45') { 8166 } else { throw 'Unknown SOS kind' }
    $owned = $false; $identityError = $null
    try { $procs = @(Get-AaProcesses $Kind); $owned = $procs.Count -eq 1 -and (Test-AaPort $port $procs) }
    catch { $identityError = $_.Exception.Message }
    $listening = @(Get-PortOwner $port).Count -gt 0
    if ($listening -and -not $owned) {
        return [pscustomobject]@{Action='warn_unidentified_occupant';Port=$port;IdentityError=$identityError}
    }
    if ($listening -and $owned) { return [pscustomobject]@{Action='retain';Port=$port;IdentityError=$identityError} }
    return [pscustomobject]@{Action='start';Port=$port;IdentityError=$identityError}
}
function Test-SosHealthy([string]$Kind, [hashtable]$Headers) {
    # True only when healthz succeeds AND (for sos45) the live database_name is the
    # isolated acceptance DB. A 'db: ok' response alone is never sufficient for sos45.
    $port = if ($Kind -eq 'sos') { 8165 } else { 8166 }
    $h = Get-HttpJson "http://127.0.0.1:$port/api/healthz" $Headers
    if (-not $h -or $h.db -ne 'ok') { return $false }
    if ($Kind -eq 'sos45') { return $h.database_name -eq 'ltc_sos45_acceptance' }
    return $true
}
function Get-JiaanStatus {
    $rows = @()
    # Migrated off Docker (2026-11-21): DB is WSL-native PostgreSQL (Ubuntu-22.04, port 55432),
    # the same instance start_all_no_docker.ps1 manages. A listening port plus the API's own
    # db='ok' healthz check (done in the 'api' row below) together stand in for the old
    # docker inspect health check; this row only confirms the port side.
    $dbOk = @(Get-PortOwner 55432).Count -gt 0
    $rows += [pscustomobject]@{Service='DB';Result=$(if($dbOk){'PASS'}else{'FAIL'});Detail='aa: WSL native PostgreSQL / 127.0.0.1:55432'}
    $ollama = Get-HttpJson 'http://127.0.0.1:11434/api/tags'
    $modelOk = $ollama -and @($ollama.models | Where-Object name -eq 'gemma4:e4b').Count -gt 0
    $rows += [pscustomobject]@{Service='Ollama';Result=$(if($ollama){'PASS'}else{'FAIL'});Detail='127.0.0.1:11434'}
    $rows += [pscustomobject]@{Service='Model';Result=$(if($modelOk){'PASS'}else{'FAIL'});Detail='gemma4:e4b available (not an inference test)'}
    $stt = Get-HttpJson 'http://127.0.0.1:8147/healthz'
    $api = Get-HttpJson 'http://127.0.0.1:8140/api/healthz' (Get-InternalHealthHeaders)
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
    $headers = Get-InternalHealthHeaders
    foreach ($kind in 'sos','sos45') {
        $decision = Get-SosStartDecision $kind
        $detail = "port=$($decision.Port) action=$($decision.Action)"
        if ($decision.Action -eq 'warn_unidentified_occupant') {
            # Port is held by something our identity check cannot vouch for. Never treat
            # this as healthy and never attempt to (re)launch into an occupied port.
            $rows += [pscustomobject]@{Service=$kind.ToUpper();Result='FAIL';Detail="$detail; WARNING unidentified occupant, refusing to start or claim ownership"}
            continue
        }
        $ok = $decision.Action -eq 'retain' -and (Test-SosHealthy $kind $headers)
        $h = Get-HttpJson "http://127.0.0.1:$($decision.Port)/api/healthz" $headers
        if ($h) { $detail += "; database_name=$($h.database_name)" }
        else { $detail += '; healthz query failed: ' + $script:HttpFailures["http://127.0.0.1:$($decision.Port)/api/healthz"] }
        $rows += [pscustomobject]@{Service=$kind.ToUpper();Result=$(if($ok){'PASS'}else{'FAIL'});Detail=$detail}
    }
    $funnelOk = Test-Funnel
    $rows += [pscustomobject]@{Service='Funnel';Result=$(if($funnelOk){'PASS'}else{'FAIL'});Detail=$(if($funnelOk){'HTTPS 443 -> sixth 29140; external reachability needs phone test'}else{'Funnel unavailable; autostart retries persistent --bg configuration'})}
    return $rows
}
function Get-LaunchSpec([string]$Kind) {
    $exe = if($Kind -eq 'stt'){$script:AsrPython}else{$script:BackendPython}
    $cwd = if($Kind -eq 'stt'){$script:Root}else{Join-Path $script:Root 'backend'}
    $args = switch($Kind) {
        'api' { @('-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8140') }
        'worker' { @('-B','-m','app.worker') }
        'stt' { @('-B',(Join-Path $script:Root 'services\stt_sidecar\server.py'),'--host','127.0.0.1','--port','8147','--model','medium','--device','cuda') }
        'sos' { @('-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8165','--no-access-log') }
        'sos45' { @('-B','-m','uvicorn','sos45_isolated_api:app','--host','127.0.0.1','--port','8166','--no-access-log') }
        default { throw 'Unknown service' }
    }
    function Quote-PS([string]$s) { "'" + $s.Replace("'","''") + "'" }
    $log = Join-Path $script:LogDir "$Kind.log"
    $command = '$ErrorActionPreference=''Continue''; $env:PYTHONUTF8=''1''; $env:PYTHONIOENCODING=''utf-8''; ' +
        'Set-Location -LiteralPath ' + (Quote-PS $cwd) + '; & ' + (Quote-PS $exe) + ' ' +
        (($args | ForEach-Object { Quote-PS $_ }) -join ' ') + ' *>> ' + (Quote-PS $log) + '; exit $LASTEXITCODE'
    if($Kind -in @('api','worker','sos','sos45')){ $command = '. ' + (Quote-PS (Join-Path $PSScriptRoot 'load_webpush_runtime.ps1')) + '; ' + $command }
    # SOS/SOS45 mirror backend\recover_sos_*.ps1's existing, reviewed opt-in self-test switch:
    # dispatch stays off (set by load_webpush_runtime.ps1 above); self-test is a manager-only,
    # self-targeted push the operator must still trigger by hand (see jiaan_webpush_routes.py).
    if($Kind -in @('sos','sos45')){
        # Both external dispatch paths are fail-safe OFF in the actual child process.
        # Do not rely on a parent shell's environment or only on Python defaults.
        $command = '$env:JIAAN_WEBPUSH_SELF_TEST=''on''; $env:JIAAN_WEBPUSH_DISPATCH=''off''; ' +
            '$env:JIAAN_EMERGENCY_LINE_DISPATCH=''off''; ' + $command
    }
    [pscustomobject]@{Encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command));Exe=$exe;Kind=$Kind}
}
if (-not $Library) {
    try { $rows = @(Get-JiaanStatus); $rows | Format-Table -AutoSize; if (@($rows | Where-Object Result -eq 'FAIL').Count) { exit 1 }; exit 0 }
    catch { Write-Host 'FAIL: health check could not complete; check permissions and dependencies.'; exit 1 }
}

