$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\frontend_publish.ps1')
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('ltc-publish-tests-' + [guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($testRoot) | Out-Null
$script:passed = 0
function Assert([bool]$Value, [string]$Message) { if (-not $Value) { throw $Message } }
function Fixture([string]$Name = 'normal') {
    $root = Join-Path $testRoot ($Name + '-' + [guid]::NewGuid().ToString('N'))
    $liveDir = Join-Path $root 'dist'
    $backupDir = Join-Path $root 'backup'
    [IO.Directory]::CreateDirectory($liveDir) | Out-Null
    [IO.Directory]::CreateDirectory($backupDir) | Out-Null
    $f = @{ Live=(Join-Path $liveDir 'index.html'); Pending=(Join-Path $liveDir 'index.pending'); Backup=(Join-Path $backupDir 'index.html'); Sentinel=(Join-Path $root 'production-data.keep') }
    [IO.File]::WriteAllText($f.Live, 'old')
    [IO.File]::WriteAllText($f.Backup, 'old')
    [IO.File]::WriteAllText($f.Pending, 'new')
    [IO.File]::WriteAllText($f.Sentinel, 'do-not-change')
    return $f
}
function Check-Old($f) {
    Assert ([IO.File]::ReadAllText($f.Live) -ceq 'old') 'Live index changed on failure'
    Assert ([IO.File]::ReadAllText($f.Backup) -ceq 'old') 'Verified backup changed'
    Assert ([IO.File]::ReadAllText($f.Sentinel) -ceq 'do-not-change') 'Unrelated data changed'
}
function Reject([scriptblock]$Action) {
    $rejected = $false
    try { & $Action } catch { $rejected = $true }
    Assert $rejected 'Expected a safe failure'
}
function Test([string]$Label, [scriptblock]$Body) {
    & $Body
    $script:passed++
    Write-Output "PASS $Label"
}
Test 'original PS5 null argument error reproduced without changing index' {
    $f = Fixture
    Reject { [IO.File]::Replace($f.Pending, $f.Live, [string]::Empty) }
    Check-Old $f
    if ($PSVersionTable.PSVersion.Major -eq 5) {
        Reject { [IO.File]::Replace($f.Pending, $f.Live, $null) }
        Check-Old $f
    }
}
foreach ($name in @('normal', 'with spaces', 'brackets[1]', "quote'and&symbol", ([string][char]0x5609 + [char]0x5B89))) {
    Test "publish literal path: $name" {
        $f = Fixture $name
        Publish-FrontendIndex $f.Pending $f.Live $f.Backup { }
        Assert ([IO.File]::ReadAllText($f.Live) -ceq 'new') 'New index not published'
        Assert ([IO.File]::ReadAllText($f.Backup) -ceq 'old') 'Backup overwritten'
        Assert ([IO.File]::ReadAllText($f.Sentinel) -ceq 'do-not-change') 'Unrelated data changed'
    }
}
Test 'relative source rejected before mutation' {
    $f = Fixture
    Reject { Publish-FrontendIndex 'relative.pending' $f.Live $f.Backup { } }
    Check-Old $f
}
Test 'invalid character rejected before mutation' {
    $f = Fixture
    Reject { Publish-FrontendIndex ($f.Pending + [char]0 + 'bad') $f.Live $f.Backup { } }
    Check-Old $f
}
Test 'missing source rejected before mutation' {
    $f = Fixture
    Reject { Publish-FrontendIndex ($f.Pending + '.missing') $f.Live $f.Backup { } }
    Check-Old $f
}
Test 'source equals live rejected' {
    $f = Fixture
    Reject { Publish-FrontendIndex $f.Live $f.Live $f.Backup { } }
    Check-Old $f
}
Test 'source outside live directory rejected' {
    $f = Fixture
    Reject { Publish-FrontendIndex $f.Backup $f.Live $f.Pending { } }
    Check-Old $f
}
Test 'mismatched backup stops deployment' {
    $f = Fixture
    [IO.File]::WriteAllText($f.Backup, 'different')
    Reject { Publish-FrontendIndex $f.Pending $f.Live $f.Backup { } }
    Assert ([IO.File]::ReadAllText($f.Live) -ceq 'old') 'Index changed with invalid backup'
    Assert ([IO.File]::ReadAllText($f.Backup) -ceq 'different') 'Backup modified'
}
Test 'post-publication verification failure restores old index' {
    $f = Fixture
    Reject { Publish-FrontendIndex $f.Pending $f.Live $f.Backup { throw 'Simulated HTTP failure' } }
    Check-Old $f
}
Test 'locked destination failure preserves old index and backup' {
    $f = Fixture
    $lock = [IO.File]::Open($f.Live, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
    try { Reject { Publish-FrontendIndex $f.Pending $f.Live $f.Backup { } } }
    finally { $lock.Dispose() }
    Check-Old $f
}
Test 'Replace failure from locked pending file preserves old index' {
    $f = Fixture
    $lock = [IO.File]::Open($f.Pending, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try { Reject { Publish-FrontendIndex $f.Pending $f.Live $f.Backup { throw 'Must not reach verification' } } }
    finally { $lock.Dispose() }
    Check-Old $f
    Assert ([IO.File]::Exists($f.Pending)) 'Pending file lost on failed Replace'
}
Test 'publishing a non-index destination is rejected' {
    $f = Fixture
    Reject { Publish-FrontendIndex $f.Pending $f.Sentinel $f.Backup { } }
    Check-Old $f
}
Write-Output "Tests: $script:passed passed; fixtures retained at $testRoot"
