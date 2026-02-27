param(
  [string]$EnvFile = ".\backend\.env",
  [string]$BackendBaseUrl = "https://danieloza-ai-web.onrender.com",
  [string]$RenderApiKey = "",
  [string]$RenderWebServiceId = "",
  [switch]$SkipStripeWebhookRotate,
  [switch]$SkipGitHubSecrets,
  [switch]$SkipRenderUpdate,
  [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"

function Fail([string]$msg) {
  throw $msg
}

function Read-DotEnvMap([string]$path) {
  if (!(Test-Path $path)) {
    Fail "Missing env file: $path"
  }
  $map = [ordered]@{}
  foreach ($ln in (Get-Content $path)) {
    if ([string]::IsNullOrWhiteSpace($ln)) { continue }
    if ($ln.TrimStart().StartsWith("#")) { continue }
    if ($ln -notmatch "=") { continue }
    $parts = $ln -split "=", 2
    $k = $parts[0].Trim()
    $v = $parts[1]
    if ($k) { $map[$k] = $v }
  }
  return $map
}

function Write-DotEnvMap([string]$path, $map) {
  $out = New-Object System.Collections.Generic.List[string]
  foreach ($entry in $map.GetEnumerator()) {
    $out.Add("$($entry.Key)=$($entry.Value)")
  }
  Set-Content -Path $path -Value $out -Encoding UTF8
}

function New-HexToken([int]$bytes = 32) {
  $arr = New-Object byte[] $bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($arr)
  return (($arr | ForEach-Object { "{0:x2}" -f $_ }) -join "")
}

function Require-Command([string]$name) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if ($null -eq $cmd) {
    Fail "Command not found: $name"
  }
}

function Ensure-RenderAuth() {
  if ([string]::IsNullOrWhiteSpace($RenderApiKey)) {
    $script:RenderApiKey = [System.Environment]::GetEnvironmentVariable("RENDER_API_KEY", "Process")
  }
  if ([string]::IsNullOrWhiteSpace($RenderApiKey)) {
    Fail "Render API key missing. Pass -RenderApiKey or set RENDER_API_KEY."
  }
  if ([string]::IsNullOrWhiteSpace($RenderWebServiceId)) {
    $script:RenderWebServiceId = [System.Environment]::GetEnvironmentVariable("RENDER_WEB_SERVICE_ID", "Process")
  }
  if ([string]::IsNullOrWhiteSpace($RenderWebServiceId)) {
    Fail "Render web service id missing. Pass -RenderWebServiceId or set RENDER_WEB_SERVICE_ID."
  }
}

function Get-StripeWebhookSecret([string]$stripeKey, [string]$webhookUrl) {
  $tmp = New-TemporaryFile
  try {
    $py = @"
import json
import stripe
import sys
stripe.api_key = sys.argv[1]
url = sys.argv[2]
ep = stripe.WebhookEndpoint.create(
    url=url,
    enabled_events=["checkout.session.completed"],
    description="DANIELOZA_AI auto-rotated endpoint",
)
print(json.dumps({"id": ep.id, "secret": ep.secret}))
"@
    Set-Content -Path $tmp.FullName -Value $py -Encoding UTF8
    $raw = & .\backend\.venv\Scripts\python.exe $tmp.FullName $stripeKey $webhookUrl
    if ($LASTEXITCODE -ne 0) {
      Fail "Stripe webhook endpoint creation failed."
    }
    return ($raw | ConvertFrom-Json)
  } finally {
    Remove-Item -Path $tmp.FullName -Force -ErrorAction SilentlyContinue
  }
}

function Set-GitHubSecret([string]$name, [string]$value) {
  if ([string]::IsNullOrWhiteSpace($value)) {
    Fail "Cannot set empty GitHub secret: $name"
  }
  gh secret set $name -b $value | Out-Null
}

function Update-RenderEnv([string]$apiKey, [string]$serviceId, $setMap) {
  $headers = @("Authorization: Bearer $apiKey")
  $currentRaw = curl.exe -fsS -H $headers[0] "https://api.render.com/v1/services/$serviceId/env-vars"
  if ($LASTEXITCODE -ne 0) {
    Fail "Failed to fetch Render env vars."
  }
  $current = $currentRaw | ConvertFrom-Json
  $kv = [ordered]@{}
  foreach ($row in $current) {
    $envVar = $row.envVar
    if ($null -ne $envVar -and $envVar.key) {
      $kv[$envVar.key] = [string]$envVar.value
    }
  }
  foreach ($entry in $setMap.GetEnumerator()) {
    $kv[$entry.Key] = [string]$entry.Value
  }
  $items = @()
  foreach ($entry in $kv.GetEnumerator()) {
    $items += @{ key = $entry.Key; value = $entry.Value }
  }
  $body = $items | ConvertTo-Json -Depth 4 -Compress
  $tmpBody = New-TemporaryFile
  try {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($tmpBody.FullName, $body, $utf8NoBom)
    $resp = curl.exe -fsS -X PUT -H $headers[0] -H "Content-Type: application/json" --data-binary "@$($tmpBody.FullName)" "https://api.render.com/v1/services/$serviceId/env-vars"
    if ($LASTEXITCODE -ne 0) {
      Fail "Failed to update Render env vars."
    }
    $parsed = $resp | ConvertFrom-Json
    if ($parsed -isnot [System.Array]) {
      Fail "Render env update returned unexpected payload."
    }
    return $parsed
  } finally {
    Remove-Item -Path $tmpBody.FullName -Force -ErrorAction SilentlyContinue
  }
}

function Trigger-RenderDeploy([string]$apiKey, [string]$serviceId) {
  $resp = curl.exe -fsS -X POST `
    -H "Authorization: Bearer $apiKey" `
    -H "Content-Type: application/json" `
    "https://api.render.com/v1/services/$serviceId/deploys"
  if ($LASTEXITCODE -ne 0) {
    Fail "Failed to trigger Render deploy."
  }
  $parsed = $resp | ConvertFrom-Json
  if ($null -eq $parsed) {
    Fail "Render deploy trigger returned empty payload."
  }
}

function Invoke-BackendHealth([string]$baseUrl, [string]$adminToken) {
  $readyUrl = $baseUrl.TrimEnd("/") + "/api/ready"
  $metricsUrl = $baseUrl.TrimEnd("/") + "/api/ops/metrics"

  $readyOk = $false
  for ($i = 0; $i -lt 30; $i++) {
    try {
      $ready = Invoke-RestMethod -Method Get -Uri $readyUrl
      if ($ready.ok) {
        $readyOk = $true
        break
      }
    } catch {
      Start-Sleep -Seconds 3
      continue
    }
    Start-Sleep -Seconds 3
  }
  if (-not $readyOk) {
    Fail "/api/ready did not return ok=true in time"
  }

  for ($i = 0; $i -lt 30; $i++) {
    try {
      $metrics = Invoke-RestMethod -Method Get -Uri $metricsUrl -Headers @{ "x-admin-token" = $adminToken }
      if ($metrics.ok) {
        return
      }
    } catch {
      Start-Sleep -Seconds 3
      continue
    }
    Start-Sleep -Seconds 3
  }
  Fail "/api/ops/metrics with rotated admin token did not pass in time"
}

function Assert-RenderEnvMatches([string]$apiKey, [string]$serviceId, $expectedMap) {
  $raw = curl.exe -fsS -H "Authorization: Bearer $apiKey" "https://api.render.com/v1/services/$serviceId/env-vars"
  if ($LASTEXITCODE -ne 0) {
    Fail "Failed to verify Render env vars."
  }
  $arr = $raw | ConvertFrom-Json
  $actual = @{}
  foreach ($row in $arr) {
    $envVar = $row.envVar
    if ($null -ne $envVar -and $envVar.key) {
      $actual[$envVar.key] = [string]$envVar.value
    }
  }
  foreach ($entry in $expectedMap.GetEnumerator()) {
    $k = [string]$entry.Key
    $v = [string]$entry.Value
    if (-not $actual.ContainsKey($k)) {
      Fail "Render env missing key after update: $k"
    }
    if ($actual[$k] -ne $v) {
      Fail "Render env value mismatch for key: $k"
    }
  }
}

Require-Command "gh"
if (!(Test-Path ".\backend\.venv\Scripts\python.exe")) {
  Fail "Missing backend venv python: .\backend\.venv\Scripts\python.exe"
}

$envMap = Read-DotEnvMap $EnvFile
$adminToken = New-HexToken 32
$webhookSecret = [string]($envMap["STRIPE_WEBHOOK_SECRET"] | ForEach-Object { $_ })
$webhookEndpointId = ""

$originAllow = "$($BackendBaseUrl.TrimEnd('/')),http://127.0.0.1:5500,http://localhost:5500"

if (-not $SkipStripeWebhookRotate) {
  $stripeKey = [string]($envMap["STRIPE_SECRET_KEY"] | ForEach-Object { $_ })
  if ([string]::IsNullOrWhiteSpace($stripeKey)) {
    Fail "Missing STRIPE_SECRET_KEY in env file."
  }
  $endpoint = Get-StripeWebhookSecret -stripeKey $stripeKey -webhookUrl ($BackendBaseUrl.TrimEnd("/") + "/api/billing/stripe/webhook")
  $webhookSecret = [string]$endpoint.secret
  $webhookEndpointId = [string]$endpoint.id
}

if ([string]::IsNullOrWhiteSpace($webhookSecret)) {
  Fail "Webhook secret is empty."
}

$envMap["ADMIN_TOKEN"] = $adminToken
$envMap["STRIPE_WEBHOOK_SECRET"] = $webhookSecret
$envMap["CORS_ALLOW_ORIGINS"] = $originAllow
$envMap["PUBLIC_ORIGIN_ALLOWLIST"] = $originAllow
$envMap["AUTH_ORIGIN_ALLOWLIST"] = $originAllow
$envMap["AUTH_LOGIN_WINDOW_SECONDS"] = "900"
$envMap["AUTH_LOGIN_MAX_ATTEMPTS"] = "5"
$envMap["AUTH_LOGIN_LOCK_SECONDS"] = "1800"
$envMap["MVP_WORKER_ENABLED"] = "true"
$envMap["LEGACY_QUEUE_WORKER_ENABLED"] = "false"
Write-DotEnvMap -path $EnvFile -map $envMap

if (-not $SkipGitHubSecrets) {
  Set-GitHubSecret -name "ADMIN_TOKEN" -value $adminToken
  Set-GitHubSecret -name "BACKEND_ADMIN_TOKEN" -value $adminToken
  Set-GitHubSecret -name "BACKEND_BASE_URL" -value $BackendBaseUrl
  Set-GitHubSecret -name "STRIPE_WEBHOOK_SECRET" -value $webhookSecret
}

if (-not $SkipRenderUpdate) {
  Ensure-RenderAuth
  $renderSet = [ordered]@{
    "ADMIN_TOKEN" = $adminToken
    "STRIPE_WEBHOOK_SECRET" = $webhookSecret
    "CORS_ALLOW_ORIGINS" = $originAllow
    "AUTH_ORIGIN_ALLOWLIST" = $originAllow
    "AUTH_LOGIN_WINDOW_SECONDS" = "900"
    "AUTH_LOGIN_MAX_ATTEMPTS" = "5"
    "AUTH_LOGIN_LOCK_SECONDS" = "1800"
    "MVP_WORKER_ENABLED" = "true"
    "LEGACY_QUEUE_WORKER_ENABLED" = "false"
  }
  Update-RenderEnv -apiKey $RenderApiKey -serviceId $RenderWebServiceId -setMap $renderSet | Out-Null
  Assert-RenderEnvMatches -apiKey $RenderApiKey -serviceId $RenderWebServiceId -expectedMap $renderSet
  if (-not $SkipDeploy) {
    Trigger-RenderDeploy -apiKey $RenderApiKey -serviceId $RenderWebServiceId
  }
}

Invoke-BackendHealth -baseUrl $BackendBaseUrl -adminToken $adminToken

$maskedAdmin = $adminToken.Substring(0, 8) + "..."
$maskedWebhook = $webhookSecret.Substring(0, [Math]::Min(12, $webhookSecret.Length)) + "..."

Write-Host "Rotation completed."
Write-Host "ADMIN_TOKEN: $maskedAdmin"
Write-Host "STRIPE_WEBHOOK_SECRET: $maskedWebhook"
if ($webhookEndpointId) {
  Write-Host "Created Stripe webhook endpoint: $webhookEndpointId"
}
Write-Host "Backend health check passed."
