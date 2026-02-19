param(
  [int]$RetentionDays = 14
)

$ErrorActionPreference = "Stop"

$dbPath = ".\backend\jobs.sqlite3"
if (!(Test-Path $dbPath)) { throw "Brak bazy: $dbPath" }

$backupDir = ".\backend\backups"
if (!(Test-Path $backupDir)) {
  New-Item -ItemType Directory -Path $backupDir | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outPath = Join-Path $backupDir ("jobs-" + $stamp + ".sqlite3")
Copy-Item $dbPath $outPath -Force
Write-Host "Backup created: $outPath"

$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem $backupDir -Filter "jobs-*.sqlite3" |
  Where-Object { $_.LastWriteTime -lt $cutoff } |
  ForEach-Object {
    Remove-Item $_.FullName -Force
    Write-Host "Deleted old backup: $($_.Name)"
  }
