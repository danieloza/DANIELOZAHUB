param(
  [switch]$EnsureDeps
)

$ErrorActionPreference = "Stop"

if (!(Test-Path ".\backend")) { throw "Brak folderu backend\ w tym miejscu." }

$envFile = ".\backend\.env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $kv = $_ -split '=', 2
    $k = $kv[0].Trim()
    $v = $kv[1].Trim().Trim('"')
    if ($k) { [System.Environment]::SetEnvironmentVariable($k, $v, "Process") }
  }
}

$venv = ".\backend\.venv"
if (!(Test-Path $venv)) {
  python -m venv $venv
}

$pythonExe = Join-Path $venv "Scripts\python.exe"
if (!(Test-Path $pythonExe)) {
  throw "Brak interpretera: $pythonExe"
}

if ($EnsureDeps) {
  $reqPath = ".\backend\requirements.txt"
  if (!(Test-Path $reqPath)) { throw "Brak pliku: $reqPath" }

  $hash = (Get-FileHash $reqPath -Algorithm SHA256).Hash
  $stampPath = Join-Path $venv ".req_hash"
  $prev = ""
  if (Test-Path $stampPath) {
    $prev = (Get-Content $stampPath -Raw).Trim()
  }

  if ($hash -ne $prev) {
    & $pythonExe -m pip install --upgrade pip
    & $pythonExe -m pip install -r $reqPath
    Set-Content -Path $stampPath -Value $hash -Encoding ascii
  }
}

$script:BackendPython = $pythonExe
