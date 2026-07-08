# ── Backend Dockerfile ───────────────────────────────────────────────────────
# Python 3.11 slim image for the FastAPI ACH Payment Tracking Agent backend.
# PYTHONPATH is set so the package is importable from src/ without a wheel build.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# Prevents .pyc files and enables unbuffered stdout/stderr logging.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy only dependency files first so Docker can cache this layer independently.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Application source ────────────────────────────────────────────────────────
COPY src/ ./src/
COPY pyproject.toml README.md ./

# ── Runtime directories ───────────────────────────────────────────────────────
# Mirrors the directory layout expected by config.py (_BACKEND_ROOT = /app).
RUN mkdir -p \
    database_json \
    demo-inbox/ccd \
    demo-inbox/settlement \
    demo-inbox/scheme-reject \
    demo-inbox/returns \
    demo-inbox/processed/ccd \
    demo-inbox/under-review \
    drop/ccd/input \
    drop/ccd/processed \
    drop/ccd/under-review \
    drop/ccd/error \
    drop/returns/input \
    drop/returns/processed \
    drop/returns/error \
    drop/settlement/input \
    drop/settlement/processed \
    drop/settlement/error \
    uploaded_files/ccd \
    uploaded_files/returns \
    uploaded_files/scheme \
    uploaded_files/settlement

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "payment_tracking_agent.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
