$root = "C:\Users\syfsy\OneDrive\Desktop\DANIELOZA_AI_site"
$backend = Join-Path $root "backend"

function Kill-Port($port) {
  $conns = netstat -ano | Select-String ":$port\s"
  foreach ($c in $conns) {
    $procId = ($c -split "\s+")[-1]
    if ($procId -match "^\d+$") {
      Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
    }
  }
}

Kill-Port 8000
Kill-Port 5500

Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "cd `"$backend`"; .\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000"
)

Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "cd `"$root`"; python -m http.server 5500 --bind 127.0.0.1"
)

Write-Host "OK. Frontend: http://127.0.0.1:5500/index.html"
Write-Host "OK. Backend:  http://127.0.0.1:8000/api/health"
