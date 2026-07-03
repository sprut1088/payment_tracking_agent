"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from payment_tracking_agent import __version__
from payment_tracking_agent.api.routes import router as api_router
from payment_tracking_agent.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the background scheduler on startup; stop it on shutdown."""
    from payment_tracking_agent.scheduler.scheduler import start_scheduler, stop_scheduler

    start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ACH Payment Tracking Agent",
        version=__version__,
        description=(
            "End-to-end ACH payment flow tracking and intelligence platform.\n\n"
            "Track every payment across the full lifecycle:\n"
            "**WITH BANK** → **WITH SCHEME** → **WITH BENEFICIARY BANK** → **CLEARED / REJECTED**\n\n"
            "### Key features\n"
            "- Upload and syntax-validate CCD files; LLM suggests fixes for bad lines\n"
            "- Automatic scheme push via background scheduler\n"
            "- Return file processing with trace-number matching\n"
            "- Settlement rejection processing with LLM corrective-action guidance\n"
            "- Three configurable background schedulers (APScheduler)\n"
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "health", "description": "Service health check"},
            {"name": "CCD Upload", "description": "Upload and validate ACH CCD files"},
            {"name": "Return Files", "description": "NACHA return file upload and query"},
            {"name": "Settlement Files", "description": "Settlement rejection file upload with LLM corrective actions"},
        ],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("payment_tracking_agent.main:app", host="0.0.0.0", port=8000, reload=True)

