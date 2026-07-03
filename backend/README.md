# Backend — ACH Payment Tracking Agent

Python / FastAPI backend for the end-to-end ACH payment flow tracking platform.

Tracks every payment across the full lifecycle:
**WITH BANK → WITH SCHEME → WITH BENEFICIARY BANK → CLEARED / REJECTED**

---

## What's included

| Layer | Description |
|---|---|
| **REST API** | 9 FastAPI endpoints with Swagger UI |
| **CCD upload** | Parse, syntax-validate, LLM-fix, and persist NACHA CCD files |
| **Return file** | Parse NACHA return files, match traces, update payment status |
| **Settlement file** | Parse rejection files, call LLM for corrective actions |
| **Scheduler** | 3 APScheduler jobs — scheme push, return scan, settlement scan |
| **In-memory store** | Dict-based temp DB (upload records, return files, settlement files) |

---

## Requirements

- Python 3.11+
- (Optional) An OpenAI-compatible API key for LLM features

---

## Install

### Option A — System Python, no venv (corporate / Group Policy environments)

If PowerShell blocks `.ps1` scripts (Group Policy), skip the venv and install
directly into your system Python:

```powershell
python -m pip install -r requirements.txt
```

Or install the package in editable mode:

```powershell
python -m pip install -e .
```

> **Tip:** Always use `python -m pip` instead of calling `pip` directly — it
> guarantees you're installing into the same Python that will run the app.

### Option B — venv via cmd.exe (avoids the PS execution policy block)

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

### Option C — venv in PowerShell (requires execution policy change)

```powershell
# Run once as administrator (if permitted):
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

---

## Run

### Recommended — python -m uvicorn (works in any venv or system Python)

```powershell
python -m uvicorn payment_tracking_agent.main:app --reload --host 0.0.0.0 --port 8000
```

### Using the uvicorn CLI directly (if uvicorn is on PATH)

```powershell
uvicorn payment_tracking_agent.main:app --reload --host 0.0.0.0 --port 8000
```

### Using the package entry-point

```powershell
payment-tracking-agent
```

Once running, open:

| URL | Description |
|---|---|
| http://localhost:8000/docs | **Swagger UI** (interactive API explorer) |
| http://localhost:8000/redoc | ReDoc (alternative docs) |
| http://localhost:8000/health | Health check |
| http://localhost:8000/openapi.json | Raw OpenAPI schema |

---

## Environment variables

All settings use the `PTA_` prefix and can be set in a `.env` file in the
`backend/` directory or as real environment variables.

```env
# LLM (optional — leave unset to skip LLM features)
PTA_LLM_API_KEY=sk-...
PTA_LLM_MODEL=gpt-4o-mini
PTA_LLM_BASE_URL=                        # leave blank for OpenAI; set for Azure

# File storage directories (created automatically on first use)
PTA_UPLOAD_DIR=uploaded_files/ccd
PTA_RETURN_DIR=uploaded_files/returns
PTA_SCHEME_DIR=uploaded_files/scheme
PTA_SETTLEMENT_DIR=uploaded_files/settlement

# Scheduler drop folders (place files here for automatic processing)
PTA_RETURN_SCAN_DIR=drop/returns
PTA_SETTLEMENT_SCAN_DIR=drop/settlement

# Scheduler intervals in seconds (default 30)
PTA_RETURN_SCAN_INTERVAL_SECONDS=30
PTA_SCHEME_PUSH_INTERVAL_SECONDS=30
PTA_SETTLEMENT_SCAN_INTERVAL_SECONDS=30

# CORS (comma-separated origins)
PTA_CORS_ORIGINS=["http://localhost:5173"]
```

---

## API endpoints

### CCD Upload
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/upload/ccd` | Upload CCD file — validates, LLM-fixes errors, saves |
| `GET` | `/api/v1/uploads` | List all uploaded CCD files |
| `GET` | `/api/v1/uploads/{id}` | Full upload detail with all payment records |

### Return Files
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/upload/return` | Upload NACHA return file — matches traces, updates status |
| `GET` | `/api/v1/returns` | List processed return files |
| `GET` | `/api/v1/returns/{id}` | Return file detail |

### Settlement Files
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/upload/settlement` | Upload settlement rejection file — LLM corrective actions |
| `GET` | `/api/v1/settlements` | List processed settlement files |
| `GET` | `/api/v1/settlements/{id}` | Settlement detail with LLM suggestions |

---

## Background schedulers

Three jobs start automatically when the app boots:

| Job | Polls | What it does |
|---|---|---|
| `scheme_pusher` | in-memory store | Copies `WITH_BANK_UPLOADED` files → `scheme_dir`, advances to `WITH_SCHEME_SUBMITTED` |
| `return_file_scanner` | `drop/returns/` | Processes any new `.ach` / `.txt` files, updates matched payments |
| `settlement_scanner` | `drop/settlement/` | Processes any new `.csv` / `.txt` / `.dat` files, calls LLM, updates payments |

To trigger processing without waiting, place a file in the relevant drop folder
or use the corresponding upload API endpoint.

---

## Project structure

```
src/payment_tracking_agent/
├── main.py                  ← FastAPI app factory + scheduler lifespan
├── config.py                ← Settings (env-overridable)
├── api/routes.py            ← Thin HTTP handlers only
├── services/                ← Business logic
│   ├── upload_service.py
│   ├── return_file_service.py
│   ├── scheme_service.py
│   └── settlement_service.py
├── parsers/                 ← Pure file format parsers
│   ├── ccd.py
│   ├── return_file.py
│   └── settlement.py
├── validators/ccd_validator.py
├── agents/                  ← LLM integrations
│   ├── llm_fixer.py         ← Syntax fix suggestions
│   └── llm_advisor.py       ← Rejection corrective actions
├── models/                  ← Pydantic models
│   ├── payment.py
│   ├── validation.py
│   ├── return_file.py
│   └── settlement.py
├── ledger/store.py          ← In-memory temp DB
└── scheduler/scheduler.py  ← APScheduler jobs
```


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
