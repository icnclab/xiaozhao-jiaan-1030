# Compatibility entry point for the existing STUST installation.
# Configuration comes from the project .env; Funnel forwards HTTPS to 127.0.0.1:8140.
# Installation, database restore and credential migration are no longer performed here.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$launcher = Join-Path $PSScriptRoot 'fieldtest\start_jiaan.ps1'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw 'STUST launcher missing.'
}
& $launcher
