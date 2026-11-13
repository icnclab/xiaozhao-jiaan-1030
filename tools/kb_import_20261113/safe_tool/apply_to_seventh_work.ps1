param(
  [string]$ProjectRoot = 'C:\aa\ltc_care_installer_20260912\ltc_care'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
if (-not $ProjectRoot.TrimEnd('\').EndsWith('\ltc_care', [System.StringComparison]::OrdinalIgnoreCase)) {
  throw '專案根目錄不符合預期；禁止套用。'
}
$work = Join-Path $ProjectRoot 'run\seventh_candidate_work_20261113'
if (-not (Test-Path -LiteralPath $work -PathType Container)) {
  throw '第七版工作副本不存在；禁止套用。'
}
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'PATCH_MANIFEST.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$records = @($manifest.changed_files)
if ($records.Count -ne 4) { throw '修正包檔案數不符合預期，停止。' }

# 先核對所有檔案；在核對完成以前不改任何工作檔案。
foreach ($record in $records) {
  $path = $record.path.Replace('/', '\')
  $source = Join-Path $PSScriptRoot (Join-Path 'files' $path)
  $target = Join-Path $work $path
  if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "修正檔缺失：$path" }
  if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "第七版原檔缺失：$path" }
  $currentHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToUpperInvariant()
  $patchHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToUpperInvariant()
  if ($currentHash -ne $record.original_sha256) {
    throw "現有第七版檔案已和上傳 ZIP 不同，為避免覆蓋新修改，停止：$path"
  }
  if ($patchHash -ne $record.updated_sha256) { throw "修正包雜湊不符：$path" }
}

$backup = Join-Path $ProjectRoot ('backups\SEVENTH_PATCH_BEFORE_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
if (Test-Path -LiteralPath $backup) { throw '備份目錄已存在，停止。' }
New-Item -ItemType Directory -Path $backup -ErrorAction Stop | Out-Null
foreach ($record in $records) {
  $path = $record.path.Replace('/', '\')
  $target = Join-Path $work $path
  $saved = Join-Path $backup $path
  New-Item -ItemType Directory -Force -Path (Split-Path -Path $saved -Parent) | Out-Null
  Copy-Item -LiteralPath $target -Destination $saved -ErrorAction Stop
}
foreach ($record in $records) {
  $path = $record.path.Replace('/', '\')
  $target = Join-Path $work $path
  $source = Join-Path $PSScriptRoot (Join-Path 'files' $path)
  Copy-Item -LiteralPath $source -Destination $target -ErrorAction Stop
  $hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToUpperInvariant()
  if ($hash -ne $record.updated_sha256) {
    throw "套用後雜湊核對失敗：$path；原檔已備份至 $backup"
  }
}
Write-Host 'PASS：僅更新第七版獨立工作副本的四個檔案，雜湊完全吻合。'
Write-Host "原檔備份位置：$backup"
Write-Host '正式服務、資料庫、GitHub及main工作樹均未操作。'
