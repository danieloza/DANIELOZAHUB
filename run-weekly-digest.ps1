$ErrorActionPreference = "Stop"

. .\backend-task-bootstrap.ps1 -EnsureDeps
& $BackendPython ".\backend\weekly_digest.py"
