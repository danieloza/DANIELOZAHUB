$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. .\backend-task-bootstrap.ps1 -EnsureDeps
& $script:BackendPython -m unittest backend.api_rollout_tests -v
