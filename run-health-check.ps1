$ErrorActionPreference = "Stop"

. .\backend-task-bootstrap.ps1 -EnsureDeps
& $BackendPython ".\backend\free_alert_check.py"
