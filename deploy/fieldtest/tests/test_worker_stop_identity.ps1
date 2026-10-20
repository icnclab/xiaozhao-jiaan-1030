# Synthetic process records only. No app imports, DB, process stops or service changes.
$ErrorActionPreference='Stop'
$path=Join-Path (Split-Path $PSScriptRoot -Parent) 'stop_jiaan.ps1'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)
if($errors){throw ($errors.Message -join '; ')}
foreach($name in 'Get-VerifiedWorkerTree','Get-WorkerTreeStamp'){
    $fn=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)|Where-Object Name -eq $name
    . ([scriptblock]::Create($fn.Extent.Text))
}
$root='C:\synthetic'; $exe="$root\backend\.venv\Scripts\python.exe"; $base='C:\Python311\python.exe'
$spec=[pscustomobject]@{Exe=$exe;Encoded='synthetic-encoded'}
$record=[pscustomobject]@{Project=$root;Kind='worker';Encoded=$spec.Encoded;PID=10;Started='2026-10-16T10:00:00Z'}
function Node($Id,$Parent,$Name,$Path,$Command,$Seconds){
    [pscustomobject]@{ProcessId=$Id;ParentProcessId=$Parent;Name=$Name;ExecutablePath=$Path;CommandLine=$Command;CreationDate=([datetime]$record.Started).AddSeconds($Seconds)}
}
function Fixture {
    @( (Node 10 1 'powershell.exe' "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" "powershell $($spec.Encoded)" 0),
       (Node 11 10 'conhost.exe' "$env:SystemRoot\System32\conhost.exe" 'conhost.exe 0xffffffff -ForceV1' 1),
       (Node 12 10 'python.exe' $exe "`"$exe`" -B -m app.worker" 2),
       (Node 13 12 'python.exe' $base "`"$exe`" -B -m app.worker" 3))
}
$script:passed=0
function Check($Name,[scriptblock]$Change,[bool]$Accept=$false){
    $nodes=Fixture
    & $Change $nodes
    $ok=$false; $result=$null
    try {$result=Get-VerifiedWorkerTree $nodes $record $spec $root $base; $ok=$true} catch {}
    if($ok -ne $Accept){throw "FAIL: $Name"}
    if($Accept -and (11 -in $result.Targets.ProcessId -or ($result.Targets.ProcessId -join ',') -ne '13,12,10')){throw 'Unsafe stop targets/order'}
    $script:passed++; Write-Host "PASS: $Name"
}
Check 'normal venv and system conhost; conhost excluded' {} $true
Check 'fake conhost path' {param($n) $n[1].ExecutablePath='C:\fake\conhost.exe'}
Check 'wrong conhost parent' {param($n) $n[1].ParentProcessId=12}
Check 'console predates owner' {param($n) $n[1].CreationDate=$n[0].CreationDate.AddSeconds(-1)}
Check 'unreadable console path' {param($n) $n[1].ExecutablePath=$null}
Check 'unreadable console command' {param($n) $n[1].CommandLine=$null}
Check 'console time missing' {param($n) $n[1].CreationDate=$null}
Check 'unknown child' {param($n) $n[1].Name='unknown.exe'}
Check 'wrong base path' {param($n) $n[3].ExecutablePath='C:\fake\python.exe'}
Check 'wrong base parent' {param($n) $n[3].ParentProcessId=10}
Check 'wrong worker arguments' {param($n) $n[3].CommandLine="`"$base`" -B -m app.other"}
Check 'extra worker arguments' {param($n) $n[2].CommandLine+=' --other'}
Check 'unreadable Python' {param($n) $n[3].CommandLine=$null}
Check 'wrapper command mismatch' {param($n) $n[0].CommandLine='unrelated'}
Check 'wrapper fake path' {param($n) $n[0].ExecutablePath='C:\fake\powershell.exe'}
Check 'wrapper path unreadable' {param($n) $n[0].ExecutablePath=$null}
Check 'wrapper reused PID/time' {param($n) $n[0].CreationDate=$n[0].CreationDate.AddSeconds(1)}
Check 'child older than parent' {param($n) $n[3].CreationDate=$n[0].CreationDate}
# Additional independent tests involving inventory size and record changes.
$nodes=@(Fixture); $nodes += Node 14 10 'python.exe' $exe "`"$exe`" -B -m app.worker" 4
try {Get-VerifiedWorkerTree $nodes $record $spec $root $base|Out-Null; throw 'accepted duplicate'} catch {if($_.Exception.Message -eq 'accepted duplicate'){throw}}
$script:passed++; Write-Host 'PASS: multiple Workers refused'
$nodes=@(Fixture); $nodes += Node 15 11 'python.exe' $base "`"$base`" -B -m app.worker" 4
try {Get-VerifiedWorkerTree $nodes $record $spec $root $base|Out-Null; throw 'accepted console child'} catch {if($_.Exception.Message -eq 'accepted console child'){throw}}
$script:passed++; Write-Host 'PASS: console with child refused'
$nodes=@(Fixture); $nodes += Node 16 10 'conhost.exe' "$env:SystemRoot\System32\conhost.exe" 'conhost.exe' 4
try {Get-VerifiedWorkerTree $nodes $record $spec $root $base|Out-Null; throw 'accepted multiple consoles'} catch {if($_.Exception.Message -eq 'accepted multiple consoles'){throw}}
$script:passed++; Write-Host 'PASS: multiple consoles refused'
$record.Project='C:\wrong'
Check 'wrong project record' {}
$record.Project=$root
$a=Get-VerifiedWorkerTree (Fixture) $record $spec $root $base
$nodes=Fixture; $nodes[1].CommandLine+=' changed'
$b=Get-VerifiedWorkerTree $nodes $record $spec $root $base
if((Get-WorkerTreeStamp $a) -ceq (Get-WorkerTreeStamp $b)){throw 'Tree change missed'}
$script:passed++; Write-Host 'PASS: tree mutation detected'
Write-Host "TOTAL: $script:passed passed"
