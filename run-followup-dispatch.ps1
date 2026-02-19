$ErrorActionPreference = "Stop"

. .\backend-task-bootstrap.ps1 -EnsureDeps
& $BackendPython ".\backend\followup_dispatch.py"
