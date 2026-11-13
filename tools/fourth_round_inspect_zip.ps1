param(
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [Parameter(Mandatory = $true)][string]$Destination
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    foreach ($entry in $zip.Entries) {
        $name = $entry.FullName.Replace('/', [IO.Path]::DirectorySeparatorChar)
        if ([IO.Path]::IsPathRooted($name) -or $name.Split([IO.Path]::DirectorySeparatorChar) -contains '..') {
            throw "Unsafe ZIP entry: $($entry.FullName)"
        }
    }
} finally {
    $zip.Dispose()
}

if (Test-Path -LiteralPath $Destination) {
    throw "Destination already exists: $Destination"
}
New-Item -ItemType Directory -Path $Destination | Out-Null
Expand-Archive -LiteralPath $ZipPath -DestinationPath $Destination
Get-ChildItem -LiteralPath $Destination -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        $base = [IO.Path]::GetFullPath($Destination).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
        $full = [IO.Path]::GetFullPath($_.FullName)
        if (-not $full.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Extracted path escaped destination: $full"
        }
        [pscustomobject]@{
            RelativePath = $full.Substring($base.Length)
            Length = $_.Length
            SHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
        }
    }
