# Runs the frontend Vite dev server.
# Usage: .\scripts\dev-frontend.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root "frontend"

Push-Location $frontend
try {
    if (-not (Test-Path "node_modules")) {
        npm install
    }
    npm run dev
}
finally {
    Pop-Location
}
