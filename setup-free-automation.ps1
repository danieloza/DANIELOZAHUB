$ErrorActionPreference = "Stop"

$root = (Get-Location).Path
$healthScript = Join-Path $root "run-health-check.ps1"
$digestScript = Join-Path $root "run-weekly-digest.ps1"
$followupScript = Join-Path $root "run-followup-dispatch.ps1"
$backupScript = Join-Path $root "backup-db.ps1"
$qualityScript = Join-Path $root "run-quality-report.ps1"
$exportScript = Join-Path $root "run-export-data.ps1"

if (!(Test-Path $healthScript)) { throw "Brak pliku: $healthScript" }
if (!(Test-Path $digestScript)) { throw "Brak pliku: $digestScript" }
if (!(Test-Path $followupScript)) { throw "Brak pliku: $followupScript" }
if (!(Test-Path $backupScript)) { throw "Brak pliku: $backupScript" }
if (!(Test-Path $qualityScript)) { throw "Brak pliku: $qualityScript" }
if (!(Test-Path $exportScript)) { throw "Brak pliku: $exportScript" }

$taskHealth = "DANIELOZA_HealthCheck"
$taskDigest = "DANIELOZA_WeeklyDigest"
$taskFollowup = "DANIELOZA_FollowupDispatch"
$taskBackup = "DANIELOZA_DailyBackup"
$taskQualityDaily = "DANIELOZA_DailyQuality"
$taskQualityWeekly = "DANIELOZA_WeeklyQuality"
$taskExport = "DANIELOZA_DailyExport"

$cmdHealth = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$healthScript`""
$cmdDigest = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$digestScript`""
$cmdFollowup = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$followupScript`""
$cmdBackup = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$backupScript`" -RetentionDays 14"
$cmdQualityDaily = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$qualityScript`" -Mode daily"
$cmdQualityWeekly = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$qualityScript`" -Mode weekly"
$cmdExport = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$exportScript`""

schtasks /Create /F /TN $taskHealth /SC MINUTE /MO 30 /TR $cmdHealth | Out-Null
schtasks /Create /F /TN $taskDigest /SC WEEKLY /D MON /ST 08:00 /TR $cmdDigest | Out-Null
schtasks /Create /F /TN $taskFollowup /SC MINUTE /MO 60 /TR $cmdFollowup | Out-Null
schtasks /Create /F /TN $taskBackup /SC DAILY /ST 02:00 /TR $cmdBackup | Out-Null
schtasks /Create /F /TN $taskQualityDaily /SC DAILY /ST 09:00 /TR $cmdQualityDaily | Out-Null
schtasks /Create /F /TN $taskQualityWeekly /SC WEEKLY /D MON /ST 09:15 /TR $cmdQualityWeekly | Out-Null
schtasks /Create /F /TN $taskExport /SC DAILY /ST 02:15 /TR $cmdExport | Out-Null

Write-Host "Utworzono zadania:"
Write-Host "- $taskHealth (co 30 min)"
Write-Host "- $taskDigest (poniedzialek 08:00)"
Write-Host "- $taskFollowup (co 60 min)"
Write-Host "- $taskBackup (codziennie 02:00)"
Write-Host "- $taskExport (codziennie 02:15)"
Write-Host "- $taskQualityDaily (codziennie 09:00)"
Write-Host "- $taskQualityWeekly (poniedzialek 09:15)"

Write-Host ""
Write-Host "Status:"
schtasks /Query /TN $taskHealth /FO LIST
Write-Host ""
schtasks /Query /TN $taskDigest /FO LIST
Write-Host ""
schtasks /Query /TN $taskFollowup /FO LIST
Write-Host ""
schtasks /Query /TN $taskBackup /FO LIST
Write-Host ""
schtasks /Query /TN $taskExport /FO LIST
Write-Host ""
schtasks /Query /TN $taskQualityDaily /FO LIST
Write-Host ""
schtasks /Query /TN $taskQualityWeekly /FO LIST
