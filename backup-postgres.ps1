param(
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [string]$OutputDir = ".\backend\backups\postgres",
  [int]$RetentionDays = 14
)

$ErrorActionPreference = "Stop"

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

if (!(Test-Path $OutputDir)) {
  New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outPath = Join-Path $OutputDir ("postgres-" + $stamp + ".sql")

$args = @(
  "run", "--rm",
  "-e", "PGPASSWORD=$($cfg.Pass)",
  "postgres:16",
  "pg_dump",
  "--no-owner",
  "--no-privileges",
  "-h", $dockerHost,
  "-p", $cfg.Port,
  "-U", $cfg.User,
  "-d", $cfg.Db
)

& docker @args > $outPath
if ($LASTEXITCODE -ne 0) {
  if (Test-Path $outPath) { Remove-Item $outPath -Force }
  throw "pg_dump failed."
}

Write-Host "Postgres backup created: $outPath"

$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem $OutputDir -Filter "postgres-*.sql" |
  Where-Object { $_.LastWriteTime -lt $cutoff } |
  ForEach-Object {
    Remove-Item $_.FullName -Force
    Write-Host "Deleted old backup: $($_.Name)"
  }
