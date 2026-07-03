# Backend — ACH Payment Tracking Agent

Python backend that will host the multi-agent workflow, payment status ledger,
demo simulator, and REST API consumed by the frontend.

At this bootstrap stage the package only exposes a FastAPI application with a
health endpoint and placeholder agent modules. No ACH parsing, ledger logic,
or LLM logic is implemented yet.

## Requirements

- Python 3.11+

## Install

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Run

```powershell
uvicorn payment_tracking_agent.main:app --reload --port 8000
```

Then visit http://localhost:8000/health.

## Seed Sample Local Demo Files

Use the helper script from repo root to copy predefined sample artifacts into
`backend/demo-inbox` for phased local-folder scanning.

```powershell
.\scripts\seed-local-demo-files.ps1 -Phase clean
.\scripts\seed-local-demo-files.ps1 -Phase ccd
.\scripts\seed-local-demo-files.ps1 -Phase settlement
.\scripts\seed-local-demo-files.ps1 -Phase returns
```

`-Phase reset` remains supported as an alias for `-Phase clean`.

This step seeds placeholder files only. ACH parsing is intentionally out of
scope here.

## Test

```powershell
pytest
```

## Layout

```text
backend/
  pyproject.toml
  src/payment_tracking_agent/
    __init__.py
    main.py            FastAPI app entry
    config.py          Settings loader
    api/               HTTP routes
    agents/            Agent stubs (before/after/return/orchestrator/ai)
    parsers/           CCD / settlement / return parser stubs
    ledger/            Payment status ledger stub
    simulator/         Batch cycle simulator stub
    models/            Pydantic models
  tests/
```
