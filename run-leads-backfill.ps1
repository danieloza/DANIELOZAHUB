param(
  [int]$Limit = 5000,
  [switch]$IncludeTest,
  [switch]$IncludeSpam
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$token = ""
$envFile = ".\backend\.env"
if (Test-Path $envFile) {
  $line = (Get-Content $envFile | Where-Object { $_ -match '^ADMIN_TOKEN=' } | Select-Object -First 1)
  if ($line) { $token = ($line -split '=', 2)[1].Trim() }
}

$headers = @{ "Content-Type" = "application/json" }
if ($token) { $headers["x-admin-token"] = $token }

$body = @{
  limit = [Math]::Max(1, [Math]::Min(50000, $Limit))
  include_test = [bool]$IncludeTest
  include_spam = [bool]$IncludeSpam
  refresh_autopilot = $true
  refresh_win = $true
} | ConvertTo-Json

$uri = "http://127.0.0.1:8000/api/admin/leads/backfill"
$resp = Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -Body $body
$resp | ConvertTo-Json -Depth 6
