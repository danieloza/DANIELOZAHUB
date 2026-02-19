param(
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [switch]$SkipSync
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $projectRoot "backend\.env"
if (!(Test-Path $envPath)) { throw "Brak backend/.env" }

function Get-EnvMap {
  param([string]$Path)
  $map = @{}
  Get-Content $Path | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $kv = $_ -split '=', 2
    $k = $kv[0].Trim()
    $v = $kv[1].Trim()
    if ($k) { $map[$k] = $v }
  }
  return $map
}

function Set-Or-AppendEnv {
  param(
    [string]$Path,
    [string]$Key,
    [string]$Value
  )
  $content = Get-Content $Path
  $found = $false
  for ($i = 0; $i -lt $content.Count; $i++) {
    if ($content[$i] -match "^\s*$([Regex]::Escape($Key))\s*=") {
      $content[$i] = "$Key=$Value"
      $found = $true
      break
    }
  }
  if (-not $found) {
    $content += "$Key=$Value"
  }
  Set-Content -Path $Path -Value $content
}

$envMap = Get-EnvMap -Path $envPath
$adminToken = ""
if ($envMap.ContainsKey("ADMIN_TOKEN")) { $adminToken = [string]$envMap["ADMIN_TOKEN"] }
$adminToken = $adminToken.Trim()
if (-not $adminToken) { throw "Brak ADMIN_TOKEN w backend/.env" }

$internalToken = ""
if ($envMap.ContainsKey("AUTONOMOUS_INTERNAL_CONNECTOR_TOKEN")) { $internalToken = [string]$envMap["AUTONOMOUS_INTERNAL_CONNECTOR_TOKEN"] }
$internalToken = $internalToken.Trim()
if (-not $internalToken) {
  $internalToken = "conn_" + [Guid]::NewGuid().ToString("N")
}

Set-Or-AppendEnv -Path $envPath -Key "AUTONOMOUS_INTERNAL_CONNECTOR_TOKEN" -Value $internalToken
Set-Or-AppendEnv -Path $envPath -Key "AUTONOMOUS_CONNECTOR_DEFAULT_HEALTH_URL" -Value "http://127.0.0.1:8000/api/connectors/mock/health/google_ads"
Set-Or-AppendEnv -Path $envPath -Key "AUTONOMOUS_CONNECTOR_DEFAULT_TOKEN" -Value $internalToken

Set-Or-AppendEnv -Path $envPath -Key "AUTONOMOUS_GOOGLE_ADS_APPLY_URL" -Value "http://127.0.0.1:8000/api/connectors/mock/apply/google_ads"
Set-Or-AppendEnv -Path $envPath -Key "AUTONOMOUS_GOOGLE_ADS_HEALTH_URL" -Value "http://127.0.0.1:8000/api/connectors/mock/health/google_ads"
Set-Or-AppendEnv -Path $envPath -Key "AUTONOMOUS_GOOGLE_ADS_TOKEN" -Value $internalToken

Set-Or-AppendEnv -Path $envPath -Key "AUTONOMOUS_META_ADS_APPLY_URL" -Value "http://127.0.0.1:8000/api/connectors/mock/apply/meta_ads"
Set-Or-AppendEnv -Path $envPath -Key "AUTONOMOUS_META_ADS_HEALTH_URL" -Value "http://127.0.0.1:8000/api/connectors/mock/health/meta_ads"
Set-Or-AppendEnv -Path $envPath -Key "AUTONOMOUS_META_ADS_TOKEN" -Value $internalToken

Set-Or-AppendEnv -Path $envPath -Key "AUTONOMOUS_LINKEDIN_APPLY_URL" -Value "http://127.0.0.1:8000/api/connectors/mock/apply/linkedin"
Set-Or-AppendEnv -Path $envPath -Key "AUTONOMOUS_LINKEDIN_HEALTH_URL" -Value "http://127.0.0.1:8000/api/connectors/mock/health/linkedin"
Set-Or-AppendEnv -Path $envPath -Key "AUTONOMOUS_LINKEDIN_TOKEN" -Value $internalToken

$base = $BaseUrl.Trim().TrimEnd("/")
$headers = @{
  "Content-Type" = "application/json"
  "x-admin-token" = $adminToken
}

function Upsert-Connector {
  param(
    [string]$Channel,
    [int]$LimitPct
  )
  $payload = @{
    channel = $Channel
    provider = "mock"
    mode = "live"
    status = "enabled"
    daily_change_limit_pct = $LimitPct
  } | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "$base/api/admin/autonomous/connectors" -Headers $headers -Body $payload | Out-Null
}

Upsert-Connector -Channel "google_ads" -LimitPct 20
Upsert-Connector -Channel "meta_ads" -LimitPct 20
Upsert-Connector -Channel "linkedin" -LimitPct 15

if (-not $SkipSync) {
  Invoke-RestMethod -Method Post -Uri "$base/api/admin/autonomous/connectors/google_ads/sync" -Headers $headers | Out-Null
  Invoke-RestMethod -Method Post -Uri "$base/api/admin/autonomous/connectors/meta_ads/sync" -Headers $headers | Out-Null
  Invoke-RestMethod -Method Post -Uri "$base/api/admin/autonomous/connectors/linkedin/sync" -Headers $headers | Out-Null
}

Write-Output "LIVE connectors configured (mock endpoints): google_ads, meta_ads, linkedin"
