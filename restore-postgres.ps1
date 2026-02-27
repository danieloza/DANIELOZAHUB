param(
  [Parameter(Mandatory=$true)]
  [string]$BackupPath,
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [switch]$ResetPublicSchema
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

$psqlBase = @(
  "run", "--rm", "-i",
  "-e", "PGPASSWORD=$($cfg.Pass)",
  "postgres:16",
  "psql",
  "-v", "ON_ERROR_STOP=1",
  "-h", $dockerHost,
  "-p", $cfg.Port,
  "-U", $cfg.User,
  "-d", $cfg.Db
)

if ($ResetPublicSchema) {
  $resetSql = "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
  $resetSql | & docker @psqlBase
  if ($LASTEXITCODE -ne 0) { throw "Failed to reset public schema." }
}

Get-Content $BackupPath -Raw | & docker @psqlBase
if ($LASTEXITCODE -ne 0) {
  throw "Restore failed."
}

Write-Host "Postgres restore completed from: $BackupPath"
