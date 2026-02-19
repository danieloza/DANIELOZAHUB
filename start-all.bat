@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo [1/2] Starting backend on http://127.0.0.1:8000 ...
start "DANIELOZA Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%ROOT%'; .\start-backend.ps1"

echo [2/2] Starting frontend on http://127.0.0.1:5500 ...
start "DANIELOZA Frontend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%ROOT%'; python -m http.server 5500 --bind 127.0.0.1"

timeout /t 2 >nul
start "" "http://127.0.0.1:5500/"
start "" "http://127.0.0.1:5500/admin.html"

echo Done. Two windows opened (backend + frontend).
endlocal
