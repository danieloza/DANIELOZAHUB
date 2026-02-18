$ErrorActionPreference = "Stop"

if (!(Test-Path ".\backend")) { throw "Brak folderu backend\ w tym miejscu." }

# venv w backend/
$venv = ".\backend\.venv"
if (!(Test-Path $venv)) {
  python -m venv $venv
}

& "$venv\Scripts\python.exe" -m pip install --upgrade pip
& "$venv\Scripts\python.exe" -m pip install -r ".\backend\requirements.txt"

& "$venv\Scripts\python.exe" -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
