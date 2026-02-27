param(
  [Parameter(Mandatory=$true)]
  [string]$BackupPath,
  [string]$DatabaseUrl = $env:DATABASE_URL
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $BackupPath)) {
  throw "Backup file not found: $BackupPath"
}
if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
  throw "DATABASE_URL is required (parameter or env)."
}

function Parse-DbUrl([string]$url) {
  $u = [System.Uri]$url
  $hostName = $u.Host
  $portNum = if ($u.Port -gt 0) { [string]$u.Port } else { "5432" }
  $db = $u.AbsolutePath.TrimStart("/")
  if ([string]::IsNullOrWhiteSpace($db)) { throw "Database name missing in DATABASE_URL." }
  $parts = $u.UserInfo.Split(":", 2)
  if ($parts.Count -lt 2) { throw "DATABASE_URL must include user and password." }
  $user = [System.Uri]::UnescapeDataString($parts[0])
  $pass = [System.Uri]::UnescapeDataString($parts[1])
  return @{
    Host = $hostName
    Port = $portNum
    Db = $db
    User = $user
    Pass = $pass
  }
}

$cfg = Parse-DbUrl $DatabaseUrl
$dockerHost = $cfg.Host
if ($dockerHost -eq "127.0.0.1" -or $dockerHost -eq "localhost") {
  $dockerHost = "host.docker.internal"
}
$tmpDb = "restore_check_" + (Get-Date -Format "yyyyMMddHHmmss")

$adminPsql = @(
  "run", "--rm", "-i",
  "-e", "PGPASSWORD=$($cfg.Pass)",
  "postgres:16",
  "psql",
  "-v", "ON_ERROR_STOP=1",
  "-h", $dockerHost,
  "-p", $cfg.Port,
  "-U", $cfg.User,
  "-d", "postgres"
)

try {
  "CREATE DATABASE $tmpDb;" | & docker @adminPsql
  if ($LASTEXITCODE -ne 0) { throw "Failed to create temp DB." }

  $tmpUrl = "postgresql://$($cfg.User):$($cfg.Pass)@$($cfg.Host):$($cfg.Port)/$tmpDb"
  & .\restore-postgres.ps1 -BackupPath $BackupPath -DatabaseUrl $tmpUrl

  $checkPsql = @(
    "run", "--rm", "-i",
    "-e", "PGPASSWORD=$($cfg.Pass)",
    "postgres:16",
    "psql",
    "-tA",
    "-v", "ON_ERROR_STOP=1",
    "-h", $dockerHost,
    "-p", $cfg.Port,
    "-U", $cfg.User,
    "-d", $tmpDb
  )

  $query = "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';"
  $tables = ($query | & docker @checkPsql).Trim()
  Write-Host "Restore verification OK. public tables: $tables"
}
finally {
  "DROP DATABASE IF EXISTS $tmpDb;" | & docker @adminPsql | Out-Null
}
