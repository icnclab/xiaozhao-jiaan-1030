[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'frontend_publish.ps1')
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if ($projectRoot -ine 'C:\aa\ltc_care_installer_20260912\ltc_care') { throw 'Unexpected project root' }
$frontend = Join-Path $projectRoot 'frontend'
$dist = Join-Path $frontend 'dist'
$expectedPython = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
# Read-only runtime identity check. Do not infer the served project from identical bundles.
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8140 -ErrorAction Stop)
$owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
if ($owners.Count -ne 1) { throw 'Cannot uniquely identify API listener' }
$cursor = [int]$owners[0]
$matched = $false
$visited = @{}
while ($cursor -and -not $visited.ContainsKey($cursor) -and $visited.Count -lt 8) {
    $visited[$cursor] = $true
    $apiProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$cursor" -ErrorAction Stop
    if (-not $apiProcess.ExecutablePath -or -not $apiProcess.CommandLine) { throw 'API identity unavailable' }
    if ($apiProcess.ExecutablePath -ieq $expectedPython -and $apiProcess.CommandLine -match '\buvicorn\s+app\.main:app\b') { $matched = $true; break }
    if ($apiProcess.Name -ne 'python.exe') { break }
    $cursor = [int]$apiProcess.ParentProcessId
}
if (-not $matched) {
    throw 'API identity does not match this project; nothing deployed'
}
function Assert-ServedFile([string]$Url, [string]$Path) {
    $client = New-Object Net.WebClient
    try { $bytes = $client.DownloadData($Url) } finally { $client.Dispose() }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $actual = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '') } finally { $sha.Dispose() }
    if ($actual -ne (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash) { throw 'Served file differs from expected dist' }
}
Assert-ServedFile 'http://127.0.0.1:8140/liff' (Join-Path $dist 'index.html')
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$stage = Join-Path $frontend "dist-reviewed-$stamp"
$backup = Join-Path $projectRoot "backups\frontend-dist-$stamp"
Push-Location $frontend
try {
    & npm.cmd run build -- --outDir $stage
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed; nothing deployed' }
} finally { Pop-Location }
$index = Join-Path $stage 'index.html'
if (-not (Test-Path -LiteralPath $index -PathType Leaf)) { throw 'Build index missing' }
$assets = @([regex]::Matches([IO.File]::ReadAllText($index), '(?:src|href)="(/assets/[^" ]+)"') | ForEach-Object { $_.Groups[1].Value })
if (-not $assets.Count) { throw 'Build assets missing' }
foreach ($asset in $assets) {
    if (-not (Test-Path -LiteralPath (Join-Path $stage $asset.TrimStart('/')) -PathType Leaf)) { throw 'Referenced build asset missing' }
}
New-Item -ItemType Directory -Path (Split-Path $backup) -Force | Out-Null
Copy-Item -LiteralPath $dist -Destination $backup -Recurse
foreach ($file in Get-ChildItem -LiteralPath $dist -File -Recurse) {
    $relative = $file.FullName.Substring($dist.Length).TrimStart('\')
    if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath (Join-Path $backup $relative)).Hash) { throw 'Backup verification failed; nothing deployed' }
}
# Keep old hashed assets for already-open pages. Publish the index only after all new assets exist.
$stageAssets = @(Get-ChildItem -LiteralPath (Join-Path $stage 'assets') -File -Recurse)
foreach ($file in $stageAssets) {
    $relative = $file.FullName.Substring($stage.Length).TrimStart('\')
    $target = Join-Path $dist $relative
    if ([IO.File]::Exists($target) -and (Get-FileHash -LiteralPath $target).Hash -ne (Get-FileHash -LiteralPath $file.FullName).Hash) { throw 'Asset name collision; existing assets retained' }
}
foreach ($file in $stageAssets) {
    $relative = $file.FullName.Substring($stage.Length).TrimStart('\')
    $target = Join-Path $dist $relative
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
    if (-not [IO.File]::Exists($target)) { [IO.File]::Copy($file.FullName, $target, $false) }
}
foreach ($asset in $assets) { Assert-ServedFile ('http://127.0.0.1:8140' + $asset) (Join-Path $stage $asset.TrimStart('/')) }
$pendingIndex = Join-Path $dist "index-$stamp.pending"
Copy-Item -LiteralPath $index -Destination $pendingIndex
Publish-FrontendIndex -PendingIndex $pendingIndex -LiveIndex (Join-Path $dist 'index.html') -BackupIndex (Join-Path $backup 'index.html') -Verify {
    Assert-ServedFile 'http://127.0.0.1:8140/liff' (Join-Path $dist 'index.html')
}
Write-Output "Frontend deployed. Verified backup: $backup"
Write-Output 'No services restarted. Phone/LINE acceptance remains required.'
