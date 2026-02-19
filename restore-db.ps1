param(
  [Parameter(Mandatory=$true)]
  [string]$BackupPath
)

$ErrorActionPreference = "Stop"

$dbPath = ".\backend\jobs.sqlite3"
if (!(Test-Path $BackupPath)) { throw "Nie znaleziono backupu: $BackupPath" }
if (!(Test-Path ".\backend")) { throw "Brak folderu backend" }

if (Test-Path $dbPath) {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $safety = ".\backend\backups\jobs-pre-restore-$stamp.sqlite3"
  if (!(Test-Path ".\backend\backups")) { New-Item -ItemType Directory -Path ".\backend\backups" | Out-Null }
  Copy-Item $dbPath $safety -Force
  Write-Host "Safety backup: $safety"
}

Copy-Item $BackupPath $dbPath -Force
Write-Host "DB restored from: $BackupPath"
