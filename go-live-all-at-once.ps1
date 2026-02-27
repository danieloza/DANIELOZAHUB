param(
  [ValidateSet("render", "fly", "none")]
  [string]$Target = "render",
  [string]$EnvFile = ".\backend\.env",
  [switch]$RotateLocalSecrets,
  [switch]$SkipTests,
  [switch]$SkipBackupRestore,
  [switch]$SkipDeploy,
  [string]$BackendBaseUrl = $env:BACKEND_BASE_URL,
  [string]$BackendAdminToken = $env:BACKEND_ADMIN_TOKEN,
  [string]$RenderDeployHookUrl = $env:RENDER_DEPLOY_HOOK_URL,
  [string]$ProductionDomain = ""
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

$python = ".\backend\.venv\Scripts\python.exe"
$summary = [ordered]@{}
$failures = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

function Write-Step([string]$name) {
  Write-Host ""
  Write-Host "==> $name"
}

function Add-Warn([string]$msg) {
  $warnings.Add($msg)
  Write-Host "WARN: $msg"
}

function Add-Fail([string]$msg) {
  $failures.Add($msg)
  Write-Host "FAIL: $msg"
}

function Run-RequiredStep([string]$name, [scriptblock]$block) {
  Write-Step $name
  try {
    & $block
    $summary[$name] = "ok"
  } catch {
    $summary[$name] = "failed"
    Add-Fail("${name}: $($_.Exception.Message)")
  }
}

function Run-OptionalStep([string]$name, [scriptblock]$block) {
  Write-Step $name
  try {
    & $block
    $summary[$name] = "ok"
  } catch {
    $summary[$name] = "warn"
    Add-Warn("${name}: $($_.Exception.Message)")
  }
}

function Load-DotEnv([string]$path) {
  if (!(Test-Path $path)) {
    throw "Env file not found: $path"
  }
  Get-Content $path | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $parts = $_ -split '=', 2
    $key = $parts[0].Trim()
    $value = $parts[1]
    if ($key) {
      [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
  }
}

function Require-EnvValue([string]$name) {
  $value = [System.Environment]::GetEnvironmentVariable($name, "Process")
  if ([string]::IsNullOrWhiteSpace($value)) {
    throw "Missing required env: $name"
  }
}

function Ensure-Python() {
  if (!(Test-Path $python)) {
    throw "Python venv missing: $python"
  }
}

function Write-Report() {
  $reportDir = ".\backend\reports"
  if (!(Test-Path $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir | Out-Null
  }
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $reportPath = Join-Path $reportDir ("go-live-all-at-once-" + $stamp + ".md")

  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add("# Go-Live All-at-Once Report")
  $lines.Add("")
  $lines.Add("- timestamp: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz")")
  $lines.Add("- target: $Target")
  $lines.Add("")
  $lines.Add("## Steps")
  foreach ($entry in $summary.GetEnumerator()) {
    $lines.Add("- $($entry.Key): $($entry.Value)")
  }
  $lines.Add("")
  $lines.Add("## Failures")
  if ($failures.Count -eq 0) {
    $lines.Add("- none")
  } else {
    foreach ($item in $failures) { $lines.Add("- $item") }
  }
  $lines.Add("")
  $lines.Add("## Warnings")
  if ($warnings.Count -eq 0) {
    $lines.Add("- none")
  } else {
    foreach ($item in $warnings) { $lines.Add("- $item") }
  }

  Set-Content -Path $reportPath -Value ($lines -join [Environment]::NewLine) -Encoding UTF8
  Write-Host ""
  Write-Host "Report: $reportPath"
  return $reportPath
}

Run-RequiredStep "Load env file" {
  Load-DotEnv $EnvFile
}

Run-RequiredStep "Validate required env" {
  Require-EnvValue "DATABASE_URL"
  Require-EnvValue "STRIPE_WEBHOOK_SECRET"
  Require-EnvValue "STRIPE_SECRET_KEY"
  Require-EnvValue "ADMIN_TOKEN"
}

Run-RequiredStep "Validate python env" {
  Ensure-Python
}

if ($RotateLocalSecrets) {
  Run-OptionalStep "Rotate local secrets (.env)" {
    & .\rotate-local-secrets.ps1
  }
}

Run-RequiredStep "Py compile" {
  & $python -m py_compile .\backend\app.py .\backend\mvp_billing.py
  if ($LASTEXITCODE -ne 0) { throw "py_compile failed" }
}

Run-RequiredStep "Run migrations" {
  & $python .\backend\migrate_postgres.py
  if ($LASTEXITCODE -ne 0) { throw "migrations failed" }
}

if (!$SkipTests) {
  Run-RequiredStep "Run critical tests" {
    & $python -m unittest -q backend.mvp_critical_path_test
    if ($LASTEXITCODE -ne 0) { throw "mvp_critical_path_test failed" }
    & $python -m unittest -q backend.mvp_billing_integrity_test
    if ($LASTEXITCODE -ne 0) { throw "mvp_billing_integrity_test failed" }
  }
} else {
  $summary["Run critical tests"] = "skipped"
}

if (!$SkipBackupRestore) {
  Run-RequiredStep "Backup and restore verification" {
    & .\backup-postgres.ps1
    $backup = Get-ChildItem .\backend\backups\postgres\postgres-*.sql | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($null -eq $backup) { throw "backup file not found" }
    & .\verify-postgres-backup-restore.ps1 -BackupPath $backup.FullName
  }
} else {
  $summary["Backup and restore verification"] = "skipped"
}

if (!$SkipDeploy) {
  if ($Target -eq "render") {
    Run-OptionalStep "Deploy (Render hook)" {
      if ([string]::IsNullOrWhiteSpace($RenderDeployHookUrl)) {
        throw "RENDER_DEPLOY_HOOK_URL missing, cannot trigger Render deploy"
      }
      Invoke-RestMethod -Method Post -Uri $RenderDeployHookUrl | Out-Null
    }
  } elseif ($Target -eq "fly") {
    Run-OptionalStep "Deploy (Fly)" {
      $fly = Get-Command flyctl -ErrorAction SilentlyContinue
      if ($null -eq $fly) {
        throw "flyctl not found in PATH"
      }
      if ([string]::IsNullOrWhiteSpace($env:FLY_API_TOKEN)) {
        throw "FLY_API_TOKEN missing"
      }
      & flyctl deploy --remote-only
      if ($LASTEXITCODE -ne 0) { throw "fly deploy failed" }
    }
  } else {
    $summary["Deploy"] = "skipped"
  }
} else {
  $summary["Deploy"] = "skipped"
}

Run-OptionalStep "Post-deploy health checks" {
  if ([string]::IsNullOrWhiteSpace($BackendBaseUrl)) {
    throw "BACKEND_BASE_URL missing; skip /api/ready and /api/ops/metrics checks"
  }
  $readyUrl = "$($BackendBaseUrl.TrimEnd('/'))/api/ready"
  $ready = Invoke-RestMethod -Method Get -Uri $readyUrl
  if (-not $ready.ok) {
    throw "/api/ready returned ok=false"
  }
  if (![string]::IsNullOrWhiteSpace($BackendAdminToken)) {
    $metricsUrl = "$($BackendBaseUrl.TrimEnd('/'))/api/ops/metrics"
    $metrics = Invoke-RestMethod -Method Get -Uri $metricsUrl -Headers @{ "x-admin-token" = $BackendAdminToken }
    if (-not $metrics.ok) {
      throw "/api/ops/metrics returned ok=false"
    }
  } else {
    Add-Warn("BACKEND_ADMIN_TOKEN missing; skipped /api/ops/metrics check")
  }
}

if ([string]::IsNullOrWhiteSpace($ProductionDomain)) {
  $summary["Domain HTTPS check"] = "skipped"
} else {
  Run-OptionalStep "Domain HTTPS check" {
    Resolve-DnsName $ProductionDomain -ErrorAction Stop | Out-Null
    $resp = Invoke-WebRequest -Method Head -Uri ("https://" + $ProductionDomain) -MaximumRedirection 5
    if ($resp.StatusCode -lt 200 -or $resp.StatusCode -ge 400) {
      throw "unexpected HTTP status: $($resp.StatusCode)"
    }
  }
}

$report = Write-Report

if ($failures.Count -gt 0) {
  Write-Host ""
  Write-Host "Go-live all-at-once finished with failures."
  Write-Host "See report: $report"
  exit 1
}

Write-Host ""
Write-Host "Go-live all-at-once finished successfully."
Write-Host "See report: $report"
