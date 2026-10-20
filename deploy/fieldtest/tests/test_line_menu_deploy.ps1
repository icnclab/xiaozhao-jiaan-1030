# Only parse the deployment script and exercise a pure comparison function.
$ErrorActionPreference='Stop'
$path=Join-Path (Split-Path $PSScriptRoot -Parent) 'deploy_line_menu_worker.ps1'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)
if($errors){throw ($errors.Message -join '; ')}
Write-Host 'PASS: deployment syntax'
$fn=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)|Where-Object Name -eq 'Assert-ProtectedProcesses'
. ([scriptblock]::Create($fn.Extent.Text))
$before=@([pscustomobject]@{Name='synthetic.exe';ProcessId=1;CreationDate=[datetime]'2026-10-16T10:00:00Z';ExecutablePath='C:\synthetic.exe'})
Assert-ProtectedProcesses $before $before
Write-Host 'PASS: unchanged protected process'
foreach($case in 'missing','pid','time','path'){
    $after=@([pscustomobject]@{Name='synthetic.exe';ProcessId=1;CreationDate=$before[0].CreationDate;ExecutablePath='C:\synthetic.exe'})
    switch($case){
        missing {$after=@()}
        pid {$after[0].ProcessId=2}
        time {$after[0].CreationDate=$after[0].CreationDate.AddSeconds(1)}
        path {$after[0].ExecutablePath='C:\fake.exe'}
    }
    $refused=$false
    try {Assert-ProtectedProcesses $before $after} catch {$refused=$true}
    if(-not $refused){throw "FAIL: $case"}
    Write-Host "PASS: protected process $case refused"
}
Write-Host 'TOTAL: 6 passed; deployment body never executed'
