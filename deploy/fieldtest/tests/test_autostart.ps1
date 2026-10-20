# Dependency-free regression tests. No live service, task or production DB changes.
$ErrorActionPreference='Stop'
$fieldtest=Split-Path $PSScriptRoot -Parent
foreach($file in Get-ChildItem $fieldtest -Filter '*.ps1'){
    $tokens=$null; $errors=$null
    [System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)|Out-Null
    if($errors){throw "Parse failed: $($file.Name): $($errors.Message -join '; ')"}
}
. (Join-Path $fieldtest 'status_jiaan.ps1') -Library
. (Join-Path $fieldtest 'autostart_common.ps1')
$script:messages=@()
function Log-Start([string]$Message){$script:messages += $Message}
$script:checks=0; $script:repairs=0
Wait-JiaanReady 'Model gemma4:e4b' {
    $script:checks++; return $script:checks -ge 4
} {$script:repairs++} 6 0
if($script:checks -ne 4 -or $script:repairs -ne 3){throw 'Delayed model readiness regression'}
$script:checks=0; $exhausted=$false
try {Wait-JiaanReady 'missing model' {$script:checks++; return $false} {} 5 0}
catch {$exhausted=$_.Exception.Message -match '5 attempts'}
if(-not $exhausted -or $script:checks -ne 5){throw 'Readiness retry exhaustion regression'}
$script:checks=0
Wait-JiaanReady 'temporarily unavailable' {$script:checks++; if($script:checks -lt 3){throw 'boot race'}; return $true} {} 4 0
if($script:checks -ne 3){throw 'Readiness exception retry regression'}
$ps="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$command='[Console]::Out.WriteLine(''ok''); [Console]::Error.WriteLine(''diagnostic''); exit 7'
$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$r=Invoke-JiaanNative $ps @('-NoProfile','-EncodedCommand',$encoded)
if($r.ExitCode -ne 7 -or 'ok' -notin $r.Output -or 'diagnostic' -notin $r.Output){throw 'Native stderr/exit-code regression'}
$command='Start-Sleep -Seconds 10'
$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$r=Invoke-JiaanNative $ps @('-NoProfile','-EncodedCommand',$encoded) 1
if($r.ExitCode -ne 124){throw 'Native timeout regression'}
# Exercise quoting through a real Windows executable and script parameter binding.
$fixture=Join-Path $PSScriptRoot 'argv-fixture.tmp.ps1'
try {
    'param([string]$Value) [Console]::Out.WriteLine([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Value)))' | Set-Content -LiteralPath $fixture -Encoding UTF8
    foreach($value in @('space value','embedded "quote"','C:\space path\','')){
        $r=Invoke-JiaanNative $ps @('-NoProfile','-ExecutionPolicy','Bypass','-File',$fixture,'-Value',$value)
        $expected=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($value))
        if($r.ExitCode -ne 0 -or ($r.Output -join '') -cne $expected){throw 'Native argument quoting regression'}
    }
} finally {Remove-Item -LiteralPath $fixture -ErrorAction SilentlyContinue}
Write-Host 'PASS: parser, delayed model (4th check), exhausted model (5 checks), transient exceptions, native stderr/exit code, timeout, Windows argument quoting.'
