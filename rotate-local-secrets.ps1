$ErrorActionPreference = "Stop"

$envPath = ".\backend\.env"
if (!(Test-Path $envPath)) {
  throw "Missing file: $envPath"
}

$lines = Get-Content $envPath

function Upsert([string]$k, [string]$v) {
  $pattern = "^" + [regex]::Escape($k) + "="
  if ($lines -match $pattern) {
    $script:lines = $lines | ForEach-Object { if ($_ -match $pattern) { "$k=$v" } else { $_ } }
  } else {
    $script:lines += "$k=$v"
  }
}

$bytes = 1..32 | ForEach-Object { Get-Random -Minimum 0 -Maximum 256 }
$newAdminToken = ($bytes | ForEach-Object { "{0:x2}" -f $_ }) -join ""
$newWebhookSecret = "whsec_local_" + [Guid]::NewGuid().ToString("N")

Upsert "ADMIN_TOKEN" $newAdminToken
Upsert "STRIPE_WEBHOOK_SECRET" $newWebhookSecret

Set-Content -Path $envPath -Value $lines

Write-Host "Rotated local ADMIN_TOKEN and STRIPE_WEBHOOK_SECRET in backend/.env"
Write-Host "Reminder: rotate STRIPE_SECRET_KEY in Stripe Dashboard manually."
