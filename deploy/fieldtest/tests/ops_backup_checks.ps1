[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$count = 0
function Assert-True($condition, [string]$message) {
    if (-not $condition) { throw $message }
    $script:count++
}
$restart = Join-Path $repo 'deploy\fieldtest\restart_api_quality.ps1'
$sync = Join-Path $repo 'deploy\fieldtest\github_sync_check.ps1'
foreach ($path in @($restart, $sync)) {
    $parseErrors = $null; $tokens = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$parseErrors)
    Assert-True (@($parseErrors).Count -eq 0) "Parse failure: $path"
    if ($path -eq $restart) { $restartAst = $ast }
}
# Execute only the owner resolver extracted from the actual source AST.
# Never dot-source or execute the restart script's process-control body.
$fn = $restartAst.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Resolve-Aa8140Owner'}, $true)
Assert-True ($null -ne $fn) 'Owner resolver missing'
Invoke-Expression $fn.Extent.Text
function Get-NetTCPConnection {
    param($LocalPort, $State, $ErrorAction)
    if ($LocalPort -eq 8140) { return $script:listen8140 }
    return $script:listen8151
}
function Get-CimInstance { param($ClassName, $ErrorAction) return $script:nodes }
function Reset-Fixture {
    $script:listen8140 = @([pscustomobject]@{OwningProcess=10})
    $script:listen8151 = @([pscustomobject]@{OwningProcess=20})
    $script:nodes = @(
        [pscustomobject]@{ProcessId=10;ParentProcessId=11;ExecutablePath='C:\fixture\base\python.exe';CommandLine='python -m uvicorn app.main:app --port 8140'},
        [pscustomobject]@{ProcessId=11;ParentProcessId=12;ExecutablePath='C:\fixture\venv\python.exe';CommandLine='python -m uvicorn app.main:app --port 8140'},
        [pscustomobject]@{ProcessId=20;ParentProcessId=21;ExecutablePath='C:\fixture\base\python.exe';CommandLine='python -m uvicorn app.main:app --port 8151'}
    )
}
function Resolve-Fixture {
    Resolve-Aa8140Owner -ExpectedVenvPython 'C:\fixture\venv\python.exe' -ExpectedBasePython 'C:\fixture\base\python.exe'
}
function Assert-Rejected([string]$name) {
    $rejected = $false
    try { Resolve-Fixture | Out-Null } catch { $rejected = $true }
    Assert-True $rejected "Unsafe fixture accepted: $name"
}
Reset-Fixture
$result = Resolve-Fixture
Assert-True ($result.Base.ProcessId -eq 10 -and $result.Launcher.ProcessId -eq 11 -and $result.OwnerPid -eq 12) 'Valid independent process tree rejected'
Reset-Fixture; $script:listen8140=@(); Assert-Rejected 'no listener'
Reset-Fixture; $script:listen8140 += [pscustomobject]@{OwningProcess=30}; Assert-Rejected 'ambiguous listeners'
Reset-Fixture; $script:listen8151=@([pscustomobject]@{OwningProcess=10}); Assert-Rejected 'same port owner'
Reset-Fixture; $script:nodes[0].CommandLine='python -m uvicorn app.main:app --port 8151'; Assert-Rejected 'wrong port argument'
Reset-Fixture; $script:nodes[0].ExecutablePath=''; Assert-Rejected 'missing executable identity'
Reset-Fixture; $script:nodes[1].ExecutablePath='C:\unrelated\python.exe'; Assert-Rejected 'wrong launcher'
Reset-Fixture; $script:nodes[2].ParentProcessId=12; Assert-Rejected 'shared API/demo ancestor'
# Exercise early sync guards with a fake git function. Any mutating or unknown
# git command fails the test immediately. No real git, pytest, or push is run.
function git {
    $cmd = $args -join ' '
    $global:opsGitCalls += $cmd
    $global:LASTEXITCODE = 0
    switch ($cmd) {
        'rev-parse --is-inside-work-tree' { return 'true' }
        'status --porcelain --untracked-files=no' { if ($global:opsSyncMode -eq 'dirty') { return ' M file.py' }; return }
        'rev-parse HEAD' { return ('a' * 40) }
        'tag --points-at HEAD' { return }
        default { throw "Unexpected git operation in guard test: $cmd" }
    }
}
$fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('xiaozhao-ops-guards-' + [guid]::NewGuid().ToString('N'))
$originalLocation = Get-Location
try {
    foreach ($mode in @('missing-config','locked','dirty','untagged')) {
        $global:opsSyncMode=$mode; $global:opsGitCalls=@()
        $fixture=Join-Path $fixtureRoot $mode
        New-Item -ItemType Directory -Path (Join-Path $fixture '.claude') -Force | Out-Null
        if ($mode -ne 'missing-config') {
            '{"branch":"backup/test-only"}' | Set-Content -LiteralPath (Join-Path $fixture '.claude\github-sync.json') -Encoding UTF8
        }
        if ($mode -eq 'locked') { 'held' | Set-Content -LiteralPath (Join-Path $fixture '.claude\github-sync.lock') }
        & $sync -RepoRoot $fixture | Out-Null
        $log=Get-Content -LiteralPath (Join-Path $fixture 'deploy\fieldtest\logs\github_sync.log') -Raw
        $expected=@{'missing-config'='SKIP: no .claude';'locked'='SKIP: lock held';'dirty'='SKIP: tracked files';'untagged'='has no stable-ready-'}[$mode]
        Assert-True ($log.Contains($expected)) "Missing sync guard: $mode"
        Assert-True (-not (@($global:opsGitCalls | Where-Object {$_ -match '^(push|commit|reset|clean|checkout|switch)\b'}).Count)) "Unexpected mutation: $mode"
    }
} finally { Set-Location -LiteralPath $originalLocation }
Write-Output "PASS: $count operations backup checks; mocked process identities and isolated sync guards; no live services or databases accessed."
