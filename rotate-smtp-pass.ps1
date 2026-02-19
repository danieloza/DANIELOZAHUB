$ErrorActionPreference = "Stop"

param(
  [string]$EnvPath = ".\backend\.env"
)

if (!(Test-Path $EnvPath)) {
  if (Test-Path ".\backend\.env.example") {
    Copy-Item ".\backend\.env.example" $EnvPath
  } else {
    New-Item -ItemType File -Path $EnvPath | Out-Null
  }
}

$secure = Read-Host "Wklej nowe SMTP_PASS (ukryte)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if ([string]::IsNullOrWhiteSpace($plain)) {
  throw "SMTP_PASS nie moze byc pusty."
}

$escaped = $plain.Replace('"', '\"')
$targetLine = "SMTP_PASS=""$escaped"""
$lines = Get-Content $EnvPath -ErrorAction SilentlyContinue

if ($null -eq $lines) {
  $lines = @()
}

$found = $false
$updated = @()
foreach ($line in $lines) {
  if ($line -match '^SMTP_PASS=') {
    $updated += $targetLine
    $found = $true
  } else {
    $updated += $line
  }
}

if (-not $found) {
  $updated += $targetLine
}

Set-Content -Path $EnvPath -Value $updated -Encoding utf8
Write-Host "SMTP_PASS zaktualizowany w $EnvPath"
Write-Host "Zrestartuj backend, aby zaladowac nowy sekret."
