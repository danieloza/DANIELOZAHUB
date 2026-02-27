param(
  [string]$BackendBaseUrl = $env:BACKEND_BASE_URL,
  [string]$BackendAdminToken = $env:BACKEND_ADMIN_TOKEN,
  [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"

function Fail([string]$msg) {
  throw $msg
}

if ([string]::IsNullOrWhiteSpace($BackendBaseUrl)) {
  Fail "Missing BackendBaseUrl (arg or BACKEND_BASE_URL env)."
}
if ([string]::IsNullOrWhiteSpace($BackendAdminToken)) {
  Fail "Missing BackendAdminToken (arg or BACKEND_ADMIN_TOKEN env)."
}

$base = $BackendBaseUrl.TrimEnd("/")
$headers = @{ "x-admin-token" = $BackendAdminToken }

$ready = Invoke-RestMethod -Method Get -Uri "$base/api/ready"
$metrics = Invoke-RestMethod -Method Get -Uri "$base/api/ops/metrics" -Headers $headers
$dead = Invoke-RestMethod -Method Get -Uri "$base/api/ops/dead-letters?limit=25" -Headers $headers
$failedWebhooks = Invoke-RestMethod -Method Get -Uri "$base/api/ops/webhook-events?status=failed&limit=10" -Headers $headers

$summary = [ordered]@{
  timestamp_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  backend_base_url = $base
  ready_ok = [bool]$ready.ok
  db_ok = [bool]$ready.db_ok
  worker_running = [bool]$ready.worker_running
  worker_last_heartbeat = $ready.worker_last_heartbeat
  worker_recovered_total = [int]$metrics.worker.recovered_total
  worker_recovered_last_summary = $metrics.worker.recovered_last_summary
  queue_depth = $metrics.queue_depth
  webhook_failed_last_hour = [int]$metrics.webhook_failed_last_hour
  jobs_failed_last_hour = [int]$metrics.jobs_failed_last_hour
  dead_letters_last_24h = [int]$metrics.dead_letters_last_24h
  recent_failed_webhooks = @($failedWebhooks.rows | Select-Object -First 10)
  recent_dead_letters = @($dead.rows | Select-Object -First 10)
}

$json = $summary | ConvertTo-Json -Depth 8

if ([string]::IsNullOrWhiteSpace($OutFile)) {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $OutFile = ".\backend\reports\incident-triage-$stamp.json"
}
$dir = Split-Path -Parent $OutFile
if ($dir -and !(Test-Path $dir)) {
  New-Item -ItemType Directory -Path $dir | Out-Null
}
Set-Content -Path $OutFile -Value $json -Encoding UTF8

Write-Host "Incident triage saved: $OutFile"
Write-Host "ready_ok=$($summary.ready_ok) db_ok=$($summary.db_ok) worker_running=$($summary.worker_running)"
Write-Host "queued=$($summary.queue_depth.queued) failed_webhooks_1h=$($summary.webhook_failed_last_hour) failed_jobs_1h=$($summary.jobs_failed_last_hour) dead_letters_24h=$($summary.dead_letters_last_24h)"
Write-Host "failed_webhooks_sample=$($summary.recent_failed_webhooks.Count) recovered_total=$($summary.worker_recovered_total)"
