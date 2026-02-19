param(
  [int]$Days = 1
)

$ErrorActionPreference = "Stop"

. .\backend-task-bootstrap.ps1 -EnsureDeps
& $BackendPython ".\backend\pipeline_report.py" $Days
