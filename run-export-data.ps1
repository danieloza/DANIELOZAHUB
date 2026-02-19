$ErrorActionPreference = "Stop"

. .\backend-task-bootstrap.ps1 -EnsureDeps
& $BackendPython ".\backend\export_data.py"
