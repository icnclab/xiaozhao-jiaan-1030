[CmdletBinding()]
param(
    [string]$RepoRoot = 'C:\aa\ltc_care_installer_20260912\ltc_care'
)
$ErrorActionPreference = 'Stop'

$logDir = Join-Path $RepoRoot 'deploy\fieldtest\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$logFile = Join-Path $logDir 'github_sync.log'
$lockFile = Join-Path $RepoRoot '.claude\github-sync.lock'

function Write-Log {
    param([string]$Msg)
    $line = "$(Get-Date -Format o) $Msg"
    Add-Content -LiteralPath $logFile -Encoding UTF8 -Value $line
    Write-Host $line
}

# Independent script used by BOTH the Claude Code SessionEnd hook and the daily
# Windows Task Scheduler job. A lock file prevents the two triggers from running
# this at the same time.
New-Item -ItemType Directory -Force (Split-Path $lockFile) | Out-Null
if (Test-Path -LiteralPath $lockFile) {
    $lockAge = (Get-Date) - (Get-Item -LiteralPath $lockFile).LastWriteTime
    if ($lockAge.TotalMinutes -lt 20) {
        Write-Log "SKIP: lock held (age $([int]$lockAge.TotalMinutes) min) - another sync run in progress"
        exit 0
    }
    Write-Log "WARN: stale lock (age $([int]$lockAge.TotalMinutes) min) found, removing"
}
Set-Content -LiteralPath $lockFile -Value "$PID $(Get-Date -Format o)"

try {
    try {
        Set-Location -LiteralPath $RepoRoot
    } catch {
        Write-Log "SKIP: cannot cd to $RepoRoot"
        exit 0
    }

    $cfgPath = Join-Path $RepoRoot '.claude\github-sync.json'
    if (-not (Test-Path -LiteralPath $cfgPath)) {
        Write-Log "SKIP: no .claude\github-sync.json config, nothing configured to sync"
        exit 0
    }
    $cfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $targetBranch = $cfg.branch
    if (-not $targetBranch) {
        Write-Log "SKIP: github-sync.json has no 'branch' field"
        exit 0
    }

    $prevEap0 = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    git rev-parse --is-inside-work-tree 2>$null 1>$null
    $isRepo = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEap0
    if (-not $isRepo) {
        Write-Log "SKIP: $RepoRoot is not a git repository"
        exit 0
    }

    # Never auto-commit. Only ever sync a commit that is already made, clean,
    # and explicitly marked stable by a stable-ready-* tag on HEAD. Untracked
    # scratch files (zips, backups, .before_* copies) are normal in this repo
    # and are never part of what gets pushed, so only tracked-file changes
    # (modified/staged, not committed) count as "dirty" here.
    $status = git status --porcelain --untracked-files=no
    if ($status) {
        Write-Log "SKIP: tracked files have uncommitted changes - will not auto-commit, run /github-sync manually when ready"
        exit 0
    }

    $headCommit = (git rev-parse HEAD).Trim()
    $headTagsRaw = git tag --points-at HEAD
    $stableTags = @($headTagsRaw -split "`n" | Where-Object { $_ -like 'stable-ready-*' })
    if (-not $stableTags -or $stableTags.Count -eq 0) {
        Write-Log "SKIP: HEAD ($headCommit) has no stable-ready-* tag - nothing explicitly marked stable to sync"
        exit 0
    }
    $tagUsed = $stableTags[0]

    git fetch origin 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Log "STOP: git fetch origin failed (network/auth) - commit=$headCommit tag=$tagUsed branch=$targetBranch"
        exit 1
    }

    $remoteRef = "origin/$targetBranch"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    git rev-parse --verify $remoteRef 2>$null 1>$null
    $remoteExists = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEap

    if ($remoteExists) {
        git merge-base --is-ancestor $headCommit $remoteRef
        if ($LASTEXITCODE -eq 0) {
            Write-Log "SKIP: HEAD ($headCommit) already included in $remoteRef - nothing new to sync"
            exit 0
        }
        $diffBase = $remoteRef
    } else {
        $diffBase = (git rev-list --max-parents=0 HEAD | Select-Object -Last 1).Trim()
    }

    $secretPattern = 'AKIA[0-9A-Z]{16}|BEGIN (RSA|PRIVATE|OPENSSH) PRIVATE KEY|xox[baprs]-|postgresql://[^@]*:[^@]*@|password\s*=\s*"[^"$]|api[_-]?key\s*[:=]\s*"[^"$]'
    $hits = git diff "$diffBase..$headCommit" -G $secretPattern --stat 2>&1
    if ($hits) {
        Write-Log "STOP: secret-pattern scan matched content in the diff to be pushed (commit=$headCommit tag=$tagUsed) - push blocked, review manually. Details withheld from this log on purpose."
        exit 1
    }

    Write-Log "RUN: backend pytest (commit=$headCommit tag=$tagUsed)"
    Push-Location (Join-Path $RepoRoot 'backend')
    & '.\.venv\Scripts\python.exe' -m pytest -q
    $pytestExit = $LASTEXITCODE
    Pop-Location
    if ($pytestExit -ne 0) {
        Write-Log "STOP: backend pytest failed (exit $pytestExit) - commit=$headCommit tag=$tagUsed"
        exit 1
    }

    Write-Log "RUN: frontend tsc --noEmit"
    Push-Location (Join-Path $RepoRoot 'frontend')
    & npx tsc --noEmit
    $tscExit = $LASTEXITCODE
    if ($tscExit -ne 0) {
        Pop-Location
        Write-Log "STOP: frontend tsc --noEmit failed (exit $tscExit) - commit=$headCommit tag=$tagUsed"
        exit 1
    }

    Write-Log "RUN: frontend vitest"
    & npx vitest run --environment jsdom
    $vitestExit = $LASTEXITCODE
    Pop-Location
    if ($vitestExit -ne 0) {
        Write-Log "STOP: frontend vitest failed (exit $vitestExit) - commit=$headCommit tag=$tagUsed"
        exit 1
    }

    Write-Log "PUSH: origin HEAD:$targetBranch (commit=$headCommit tag=$tagUsed) - non-force"
    git push origin "HEAD:$targetBranch"
    if ($LASTEXITCODE -ne 0) {
        Write-Log "STOP: git push rejected (likely non-fast-forward / diverged remote) - manual review required, commit=$headCommit tag=$tagUsed branch=$targetBranch"
        exit 1
    }

    git fetch origin 2>&1 | Out-Null
    $remoteHead = (git rev-parse $remoteRef).Trim()
    if ($remoteHead -eq $headCommit) {
        Write-Log "OK: pushed commit=$headCommit tag=$tagUsed to $remoteRef, verified match"
    } else {
        Write-Log "WARN: pushed commit=$headCommit tag=$tagUsed but remote ($remoteHead) does not match local HEAD - verify manually"
    }
}
finally {
    Remove-Item -LiteralPath $lockFile -ErrorAction SilentlyContinue
}
