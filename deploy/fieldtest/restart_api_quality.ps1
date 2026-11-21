[CmdletBinding()]
param([switch]$DryRun, [switch]$Library)
$ErrorActionPreference = 'Stop'
$restartApiDryRun = [bool]$DryRun
$restartApiLibrary = [bool]$Library
if ($restartApiDryRun -and $restartApiLibrary) { throw 'DryRun and Library modes are mutually exclusive' }
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

function Get-VerifiedApiStopPlan {
    param(
        [object[]]$All, $Owner, $Resolved,
        [string]$ExpectedOwnerExe, [string]$ExpectedVenvPython, [string]$ExpectedBasePython,
        [string]$ExpectedEncodedCommand, [datetime]$ExpectedOwnerStart
    )
    if (-not $Owner -or -not $Resolved -or -not $Resolved.Launcher -or -not $Resolved.Base) {
        throw 'API process identity is incomplete'
    }
    if ($Owner.ExecutablePath -ine $ExpectedOwnerExe -or
        $Owner.CommandLine -notlike "* $ExpectedEncodedCommand*" -or
        [math]::Abs(($Owner.CreationDate.ToUniversalTime() - $ExpectedOwnerStart.ToUniversalTime()).TotalMilliseconds) -gt 1) {
        throw 'API owner identity mismatch'
    }
    $launcher = $Resolved.Launcher
    $base = $Resolved.Base
    if ($launcher.ParentProcessId -ne $Owner.ProcessId -or
        $launcher.ExecutablePath -ine $ExpectedVenvPython -or
        $launcher.CommandLine -notmatch 'uvicorn\s+app\.main:app\b' -or
        $launcher.CommandLine -notmatch '--port\s+8140\b') {
        throw 'API launcher identity mismatch'
    }
    if ($base.ParentProcessId -ne $launcher.ProcessId -or
        $base.ExecutablePath -ine $ExpectedBasePython -or
        $base.CommandLine -notmatch 'uvicorn\s+app\.main:app\b' -or
        $base.CommandLine -notmatch '--port\s+8140\b') {
        throw 'API base interpreter identity mismatch'
    }
    if ($launcher.CreationDate -lt $Owner.CreationDate -or $base.CreationDate -lt $launcher.CreationDate) {
        throw 'Unexpected API process start order'
    }

    # Only the exact launcher -> base chain belongs to the API stop plan. The PowerShell
    # owner can also parent unrelated desktop programs (for example Docker Desktop).
    # Never recurse through the owner's descendants and never add those programs to stops.
    $launcherChildren = @($All | Where-Object ParentProcessId -eq $launcher.ProcessId)
    if ($launcherChildren.Count -ne 1 -or $launcherChildren[0].ProcessId -ne $base.ProcessId) {
        throw 'Unexpected API launcher descendants'
    }
    if (@($All | Where-Object ParentProcessId -eq $base.ProcessId).Count) {
        throw 'Unexpected API base interpreter descendants'
    }

    # Validate the owner's direct console when present, but never stop it explicitly.
    # Other direct owner children remain outside the API plan and are audit evidence only.
    $directChildren = @($All | Where-Object ParentProcessId -eq $Owner.ProcessId)
    $directConsoles = @($directChildren | Where-Object Name -ieq 'conhost.exe')
    if ($directConsoles.Count -gt 1) { throw 'Unexpected direct API console count' }
    foreach ($console in $directConsoles) {
        if (-not $console.ExecutablePath -or -not $console.CreationDate -or
            $console.ExecutablePath -ine "$env:SystemRoot\System32\conhost.exe" -or
            $console.CreationDate -lt $Owner.CreationDate) {
            throw 'Unexpected direct API console identity'
        }
    }
    $unrelated = @($directChildren | Where-Object {
        $_.ProcessId -ne $launcher.ProcessId -and $_.ProcessId -notin @($directConsoles.ProcessId)
    })
    [pscustomobject]@{
        StopTargets = @($base, $launcher)
        Owner = $Owner
        DirectConsole = @($directConsoles)
        ExcludedOwnerChildren = @($unrelated)
    }
}

function Write-DryRunSuccess($Resolved, $Plan, [string]$ScriptPath) {
    $scriptHash = (Get-FileHash -LiteralPath $ScriptPath -Algorithm SHA256).Hash
    Write-Output "PASS：API restart DryRun 完整驗證成功；script_sha256=$scriptHash"
    Write-Output "DRY RUN：8140 base pid=$($Resolved.Base.ProcessId) launcher pid=$($Resolved.Launcher.ProcessId) owner pid=$($Resolved.OwnerPid)"
    Write-Output "DRY RUN：停止清單僅包含 base/launcher；排除 owner 其他直屬程序 $($Plan.ExcludedOwnerChildren.Count) 個。"
    Write-Output 'DRY RUN：唯一辨識與停止範圍驗證成功，未停止或啟動任何行程。'
}

# status_jiaan.ps1 is dot-sourced with its own -Library parameter. Use the value captured
# before dot-sourcing so the imported script cannot turn a normal DryRun into a silent return.
if ($restartApiLibrary) { return }

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
    $health = Get-HttpJson 'http://127.0.0.1:8140/api/healthz' (Get-InternalHealthHeaders)
    if (-not $health -or $health.database_name -ne 'ltc_clean') { throw 'Runtime is not ltc_clean' }
    $plan = Get-VerifiedApiStopPlan -All $all -Owner $owner -Resolved $resolved `
        -ExpectedOwnerExe $expectedExe -ExpectedVenvPython $venvPython -ExpectedBasePython $basePython `
        -ExpectedEncodedCommand $spec.Encoded -ExpectedOwnerStart ([datetime]$record.Started)
    if ($restartApiDryRun) {
        Write-DryRunSuccess -Resolved $resolved -Plan $plan -ScriptPath $PSCommandPath
        exit 0
    }

    # Pin only the verified API base, launcher and owner identities. The owner is pinned
    # for change detection but is never sent to Stop-Process. Docker Desktop/WSL and every
    # unrelated owner child are excluded by construction.
    $targets = @($plan.StopTargets)
    $pinned = @()
    foreach ($target in @($targets) + @($owner)) {
        $live = Get-Process -Id $target.ProcessId -ErrorAction Stop
        if ([math]::Abs(($live.StartTime.ToUniversalTime() - $target.CreationDate.ToUniversalTime()).TotalMilliseconds) -gt 1) { throw 'Process identity changed' }
        $pinned += $live
    }

    # Refuse if the port or the exact API chain changed after pinning.
    $fresh = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $freshOwner = $fresh | Where-Object ProcessId -eq $owner.ProcessId | Select-Object -First 1
    $freshResolved = Resolve-Aa8140Owner -ExpectedVenvPython $venvPython -ExpectedBasePython $basePython
    $null = Get-VerifiedApiStopPlan -All $fresh -Owner $freshOwner -Resolved $freshResolved `
        -ExpectedOwnerExe $expectedExe -ExpectedVenvPython $venvPython -ExpectedBasePython $basePython `
        -ExpectedEncodedCommand $spec.Encoded -ExpectedOwnerStart ([datetime]$record.Started)

    # Stop the verified leaf interpreter first. Its synchronous parents should exit
    # naturally. If the verified venv launcher remains, stop that exact pinned process.
    $baseLive = $pinned | Where-Object Id -eq $resolved.Base.ProcessId
    $launcherLive = $pinned | Where-Object Id -eq $resolved.Launcher.ProcessId
    $ownerLive = $pinned | Where-Object Id -eq $owner.ProcessId
    Stop-Process -InputObject $baseLive -ErrorAction Stop
    $launcherLive.WaitForExit(5000) | Out-Null
    if (-not $launcherLive.HasExited) { Stop-Process -InputObject $launcherLive -ErrorAction Stop }
    $ownerLive.WaitForExit(5000) | Out-Null
    if (-not $ownerLive.HasExited) { throw 'API owner did not exit naturally; refusing to stop owner or launch duplicate API' }
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
        $combinedRoutesLoaded = $false
        try {
            Invoke-WebRequest -Uri 'http://127.0.0.1:8140/api/qa/supervisor-ask' -Method Post `
                -ContentType 'application/json' -Body '{"question":"route probe","source":"typed","client_request_id":"deploy-route-probe"}' `
                -TimeoutSec 5 -UseBasicParsing | Out-Null
        } catch {
            if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 401) {
                try {
                    Invoke-WebRequest -Uri 'http://127.0.0.1:8140/api/admin/versions/00000000-0000-0000-0000-000000000000/file' `
                        -Method Get -TimeoutSec 5 -UseBasicParsing | Out-Null
                } catch {
                    if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 401) { $combinedRoutesLoaded = $true }
                }
            }
        }
        if ($health -and $health.database_name -eq 'ltc_clean' -and $qualityLoaded -and $combinedRoutesLoaded) {
            Write-Host 'PASS: aa API reloaded quality + third/fourth-round routes; ltc_clean retained; worker/STT/LINE settings/Tailscale untouched.'
            exit 0
        }
    } while ((Get-Date) -lt $deadline)
    throw 'API health or quality endpoint verification failed'
} catch {
    Write-Error -ErrorRecord $_ -ErrorAction Continue
    exit 1
} finally { if ($lock) { $lock.Dispose() } }
