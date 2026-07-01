# Runs the backend FastAPI app locally with reload.
# Usage: .\scripts\dev-backend.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"

Push-Location $backend
try {
    if (-not (Test-Path ".venv")) {
        python -m venv .venv
    }
    & .\.venv\Scripts\Activate.ps1
    pip install -e ".[dev]"
    uvicorn payment_tracking_agent.main:app --reload --port 8000
}
finally {
    Pop-Location
}
