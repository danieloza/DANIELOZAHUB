param(
  [ValidateSet("daily", "weekly")]
  [string]$Mode = "daily"
)

$ErrorActionPreference = "Stop"

. .\backend-task-bootstrap.ps1 -EnsureDeps
& $BackendPython ".\backend\quality_report.py" $Mode
