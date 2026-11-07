[CmdletBinding()]
param([switch]$DryRun)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'status_jiaan.ps1') -Library
$recordFile = Join-Path $script:RunDir 'api.json'
$lock = $null

# 8140（正式 API）跟 8151（示範站）是同一個 venv、同一種 uvicorn 指令啟動的兩個獨立行程；
# 光看行程名稱或「uvicorn app.main:app」字串無法唯一分辨兩者，必須連埠號、完整執行檔路徑、
# 父子行程鏈一起核對，任何一步兜不起來就直接拒絕（丟例外），不猜測、不選一個比較像的。
function Resolve-Aa8140Owner {
    param([string]$ExpectedVenvPython, [string]$ExpectedBasePython)

    $listeners8140 = @(Get-NetTCPConnection -LocalPort 8140 -State Listen -ErrorAction Stop)
    if ($listeners8140.Count -ne 1) { throw "8140 的監聽行程數量是 $($listeners8140.Count)，不是剛好一個，拒絕判定" }
    $listenerPid8140 = [int]$listeners8140[0].OwningProcess

    $listeners8151 = @(Get-NetTCPConnection -LocalPort 8151 -State Listen -ErrorAction SilentlyContinue)
    if ($listeners8151.Count -eq 1) {
        if ([int]$listeners8151[0].OwningProcess -eq $listenerPid8140) {
            throw '8140 與 8151 監聽同一個行程，拒絕判定'
        }
    }

    $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $node8140 = $all | Where-Object ProcessId -eq $listenerPid8140 | Select-Object -First 1
    if (-not $node8140) { throw '8140 監聽行程查無身分，拒絕判定' }
    if (-not $node8140.ExecutablePath) { throw '8140 監聽行程缺少執行檔路徑，拒絕判定' }
    if (-not $node8140.CommandLine) { throw '8140 監聽行程缺少指令列，拒絕判定' }
    if ($node8140.ExecutablePath -ine $ExpectedBasePython) {
        throw "8140 監聽行程不是預期的 Python 基礎執行檔（實際：$($node8140.ExecutablePath)），拒絕判定"
    }
    if ($node8140.CommandLine -notmatch 'uvicorn\s+app\.main:app\b') { throw '8140 監聽行程指令列不含 uvicorn app.main:app，拒絕判定' }
    if ($node8140.CommandLine -notmatch '--port\s+8140\b') { throw '8140 監聽行程指令列不含明確的埠號 8140，拒絕判定' }

    $launcherNode = $all | Where-Object ProcessId -eq $node8140.ParentProcessId | Select-Object -First 1
    if (-not $launcherNode) { throw '8140 的父行程（venv 啟動器）查無身分，拒絕判定' }
    if ($launcherNode.ExecutablePath -ine $ExpectedVenvPython) { throw '8140 的父行程不是預期的 venv 啟動器路徑，拒絕判定' }
    if ($launcherNode.CommandLine -notmatch 'uvicorn\s+app\.main:app\b') { throw '8140 的父行程指令列不含 uvicorn app.main:app，拒絕判定' }
    if ($launcherNode.CommandLine -notmatch '--port\s+8140\b') { throw '8140 的父行程指令列不含明確的埠號 8140，拒絕判定' }

    if ($listeners8151.Count -eq 1) {
        $pid8151 = [int]$listeners8151[0].OwningProcess
        $chain8140 = @([int]$node8140.ProcessId, [int]$launcherNode.ProcessId, [int]$launcherNode.ParentProcessId)
        $cursor = $pid8151
        $hops = 0
        while ($cursor -and $hops -lt 10) {
            if ($chain8140 -contains $cursor) { throw '8151 的行程鏈跟 8140 共用節點，無法安全判定為兩個獨立服務，拒絕操作' }
            $node = $all | Where-Object ProcessId -eq $cursor | Select-Object -First 1
            if (-not $node) { break }
            $cursor = [int]$node.ParentProcessId
            $hops = $hops + 1
        }
    }

    $out = New-Object psobject
    $out | Add-Member -NotePropertyName Base -NotePropertyValue $node8140
    $out | Add-Member -NotePropertyName Launcher -NotePropertyValue $launcherNode
    $out | Add-Member -NotePropertyName OwnerPid -NotePropertyValue ([int]$launcherNode.ParentProcessId)
    return $out
}

try {
    $lock = [IO.File]::Open((Join-Path $script:RunDir 'launcher.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $record = Get-Content -LiteralPath $recordFile -Raw | ConvertFrom-Json
    $spec = Get-LaunchSpec 'api'
    if ($record.Project -ine $script:Root -or $record.Kind -ne 'api' -or $record.Encoded -cne $spec.Encoded) { throw 'API ownership record mismatch' }
    $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $owner = $all | Where-Object ProcessId -eq $record.PID | Select-Object -First 1
    $expectedExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    if (-not $owner -or $owner.ExecutablePath -ine $expectedExe -or $owner.CommandLine -notlike "* $($spec.Encoded)*" -or
        [math]::Abs(($owner.CreationDate.ToUniversalTime() - ([datetime]$record.Started).ToUniversalTime()).TotalMilliseconds) -gt 1) { throw 'API owner identity mismatch' }

    # 8140/8151 唯一辨識：連埠號＋完整執行檔路徑＋父子行程鏈一起核對（不只看行程名稱或
    # uvicorn 字串），任何一步兜不起來就拒絕，不會誤判成 8151。
    $cfgPath = Join-Path $script:Root 'backend\.venv\pyvenv.cfg'
    $baseCfg = @(Get-Content -LiteralPath $cfgPath | Where-Object { $_ -match '^executable\s*=' })
    if ($baseCfg.Count -ne 1) { throw 'Base interpreter configuration unavailable' }
    $basePython = ($baseCfg[0] -split '=', 2)[1].Trim()
    if (-not (Test-Path -LiteralPath $basePython -PathType Leaf)) { throw 'Base interpreter unavailable' }
    $venvPython = $spec.Exe
    $resolved = Resolve-Aa8140Owner -ExpectedVenvPython $venvPython -ExpectedBasePython $basePython
    if ($resolved.OwnerPid -ne [int]$owner.ProcessId) {
        throw '8140 行程鏈往上追到的 owner，跟 api.json 記錄的 owner 不是同一個行程，拒絕判定'
    }
    if ($DryRun) {
        Write-Host "DRY RUN：8140 base pid=$($resolved.Base.ProcessId) launcher pid=$($resolved.Launcher.ProcessId) owner pid=$($resolved.OwnerPid)"
        Write-Host 'DRY RUN：唯一辨識成功，未停止或啟動任何行程。'
        exit 0
    }
    $health = Get-HttpJson 'http://127.0.0.1:8140/api/healthz' (Get-InternalHealthHeaders)
    if (-not $health -or $health.database_name -ne 'ltc_clean') { throw 'Runtime is not ltc_clean' }
    $children = @(); $parents = @([int]$owner.ProcessId)
    do {
        $next = @($all | Where-Object { $_.ParentProcessId -in $parents })
        $children += $next; $parents = @($next | ForEach-Object { [int]$_.ProcessId })
    } while ($parents.Count)
    if (-not $children.Count) { throw 'API descendants missing' }
    # CPython on Windows venv: venv launcher -> base interpreter.
    # Accept exactly that pair, plus at most one direct console host.
    $pythonChildren = @($children | Where-Object { $_.Name -ieq 'python.exe' })
    $launchers = @($pythonChildren | Where-Object {
        $_.ParentProcessId -eq $owner.ProcessId -and $_.ExecutablePath -ieq $venvPython
    })
    if ($launchers.Count -ne 1 -or $pythonChildren.Count -ne 2) { throw 'Unexpected API Python process tree' }
    $launcher = $launchers[0]
    $base = @($pythonChildren | Where-Object {
        $_.ParentProcessId -eq $launcher.ProcessId -and $_.ExecutablePath -ieq $basePython
    })
    if ($base.Count -ne 1) { throw 'Unexpected API base interpreter' }
    # 跟剛才靠埠號辨識出來的 8140 行程鏈互相比對，兩條獨立路徑都要指向同一個行程，
    # PID 中途變動或兜不起來就直接拒絕，不會沿用一個可能已經不是 8140 的身分往下做。
    if ([int]$base[0].ProcessId -ne [int]$resolved.Base.ProcessId) { throw 'base 行程 PID 跟埠號辨識結果不一致，拒絕繼續' }
    if ([int]$launcher.ProcessId -ne [int]$resolved.Launcher.ProcessId) { throw 'launcher 行程 PID 跟埠號辨識結果不一致，拒絕繼續' }
    $consoleHosts = @($children | Where-Object { $_.Name -ieq 'conhost.exe' })
    if ($consoleHosts.Count -gt 1) { throw 'Unexpected API console count' }
    foreach ($child in $children) {
        if (-not $child.ExecutablePath -or -not $child.CommandLine -or -not $child.CreationDate) { throw 'Incomplete descendant identity' }
        if ($child.CreationDate -lt $owner.CreationDate) { throw 'Unexpected descendant start time' }
        if ($child.Name -ieq 'conhost.exe') {
            if ($child.ParentProcessId -ne $owner.ProcessId -or
                $child.ExecutablePath -ine "$env:SystemRoot\System32\conhost.exe" -or
                @($all | Where-Object { $_.ParentProcessId -eq $child.ProcessId }).Count) {
                throw 'Unexpected console process'
            }
        } elseif ($child.Name -ieq 'python.exe') {
            if ($child.ProcessId -notin @($launcher.ProcessId, $base[0].ProcessId) -or
                $child.CommandLine -notmatch 'uvicorn\s+app\.main:app') { throw 'Unexpected API Python arguments' }
        } else { throw 'Unexpected descendant; refusing stop' }
    }
    if (@($all | Where-Object { $_.ParentProcessId -eq $base[0].ProcessId }).Count) {
        throw 'Unexpected nested base interpreter descendants'
    }
    $targets = @($base[0], $launcher)  # base interpreter, then venv launcher
    $targets += @($owner)
    $pinned = @()
    foreach ($target in $targets) {
        $live = Get-Process -Id $target.ProcessId -ErrorAction Stop
        if ([math]::Abs(($live.StartTime.ToUniversalTime() - $target.CreationDate.ToUniversalTime()).TotalMilliseconds) -gt 1) { throw 'Process identity changed' }
        $pinned += $live
    }
    # Refuse if the tree changed after pinning the checked process identities.
    $fresh = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    foreach ($node in $children) {
        $same = @($fresh | Where-Object { $_.ProcessId -eq $node.ProcessId -and $_.ParentProcessId -eq $node.ParentProcessId -and $_.ExecutablePath -ieq $node.ExecutablePath -and $_.CommandLine -ceq $node.CommandLine })
        if ($same.Count -ne 1) { throw 'Process tree changed before stop' }
    }
    foreach ($live in $pinned) {
        if (-not $live.HasExited) { Stop-Process -InputObject $live -ErrorAction Stop }
    }
    $deadline = (Get-Date).AddSeconds(10)
    while (@(Get-PortOwner 8140).Count -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 250 }
    if (@(Get-PortOwner 8140).Count) { throw '8140 remains occupied; refusing duplicate launch' }
    $process = Start-Process -FilePath $expectedExe -ArgumentList @('-NoProfile', '-NonInteractive', '-EncodedCommand', $spec.Encoded) -WindowStyle Hidden -PassThru
    [ordered]@{ Project=$script:Root; Kind='api'; PID=$process.Id; Started=$process.StartTime.ToUniversalTime().ToString('o'); Encoded=$spec.Encoded } |
        ConvertTo-Json | Set-Content -LiteralPath $recordFile -Encoding UTF8
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Seconds 2
        $health = Get-HttpJson 'http://127.0.0.1:8140/api/healthz' (Get-InternalHealthHeaders)
        # 正式環境現在會關閉 /api/openapi.json（公開 API 文件收斂），不能再靠它確認
        # quality 端點有沒有重新載入；改成直接打 /api/quality/feedback 不帶
        # Authorization，401（已註冊、要求登入）才算確認路由真的在，跟原本「route 存在」
        # 這個檢查意圖一致，不會因為文件被關閉就誤判重啟失敗，也不會真的送出任何資料。
        $qualityLoaded = $false
        try {
            Invoke-WebRequest -Uri 'http://127.0.0.1:8140/api/quality/feedback' -Method Get -TimeoutSec 5 -UseBasicParsing | Out-Null
        } catch {
            if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 401) { $qualityLoaded = $true }
        }
        if ($health -and $health.database_name -eq 'ltc_clean' -and $qualityLoaded) {
            Write-Host 'PASS: aa API reloaded quality endpoints; ltc_clean retained; worker/STT/LINE settings/Tailscale untouched.'
            exit 0
        }
    } while ((Get-Date) -lt $deadline)
    throw 'API health or quality endpoint verification failed'
} finally { if ($lock) { $lock.Dispose() } }
