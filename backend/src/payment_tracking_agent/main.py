"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from payment_tracking_agent import __version__
from payment_tracking_agent.api.demo_flow import router as demo_flow_router
from payment_tracking_agent.api.routes import router as api_router
from payment_tracking_agent.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    app.include_router(demo_flow_router)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("payment_tracking_agent.main:app", host="0.0.0.0", port=8000, reload=True)
