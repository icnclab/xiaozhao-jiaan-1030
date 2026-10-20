# File-only publication helper. No services, network calls or database access.
function Publish-FrontendIndex {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$PendingIndex,
        [Parameter(Mandatory=$true)][string]$LiveIndex,
        [Parameter(Mandatory=$true)][string]$BackupIndex,
        [Parameter(Mandatory=$true)][scriptblock]$Verify
    )
    foreach ($path in @($PendingIndex, $LiveIndex, $BackupIndex)) {
        if (-not [IO.Path]::IsPathRooted($path)) { throw 'Index paths must be absolute' }
        if ($path.IndexOfAny([IO.Path]::GetInvalidPathChars()) -ge 0) { throw 'Invalid index path' }
        if (-not [IO.File]::Exists($path)) { throw 'Required index file missing' }
    }
    $pending = [IO.Path]::GetFullPath($PendingIndex)
    $live = [IO.Path]::GetFullPath($LiveIndex)
    $backup = [IO.Path]::GetFullPath($BackupIndex)
    if ($pending -ieq $live -or $pending -ieq $backup -or $live -ieq $backup) { throw 'Index paths must be distinct' }
    if ([IO.Path]::GetDirectoryName($pending) -ine [IO.Path]::GetDirectoryName($live)) { throw 'Pending index must be beside live index' }
    if ([IO.Path]::GetFileName($live) -cne 'index.html' -or [IO.Path]::GetFileName($backup) -cne 'index.html') { throw 'Unexpected index name' }
    if ([IO.Path]::GetDirectoryName($backup) -ieq [IO.Path]::GetDirectoryName($live)) { throw 'Backup must be outside live directory' }
    # Reject links/junctions rather than letting a path escape its checked directory.
    foreach ($path in @($pending, $live, $backup)) {
        $node = Get-Item -LiteralPath $path -Force -ErrorAction Stop
        while ($null -ne $node) {
            if ($node.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked deployment paths are not supported' }
            $node = if ($node -is [IO.FileInfo]) { $node.Directory } else { $node.Parent }
        }
    }
    if ((Get-FileHash -LiteralPath $live).Hash -ne (Get-FileHash -LiteralPath $backup).Hash) { throw 'Backup index differs from current live index' }
    $savedIndex = Join-Path ([IO.Path]::GetDirectoryName($backup)) ('index-before-publish-' + [guid]::NewGuid().ToString('N') + '.html')
    $failedIndex = Join-Path ([IO.Path]::GetDirectoryName($backup)) ('index-failed-publish-' + [guid]::NewGuid().ToString('N') + '.html')
    $published = $false
    try {
        # PS 5.1 converts $null to an empty string for this string parameter.
        # Always pass an actual, absolute backup filename, including on rollback.
        [IO.File]::Replace($pending, $live, $savedIndex)
        $published = $true
        & $Verify
    } catch {
        $failure = $_
        if ($published) {
            try { [IO.File]::Replace($savedIndex, $live, $failedIndex) }
            catch { throw "Index rollback failed; restore from verified backup: $backup" }
            if ((Get-FileHash -LiteralPath $live).Hash -ne (Get-FileHash -LiteralPath $backup).Hash) { throw "Rollback verification failed; backup: $backup" }
        }
        throw $failure
    }
}
