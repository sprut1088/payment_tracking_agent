"""Placeholder HTTP routes.

Real endpoints (upload CCD, run cycle, payment search, batch dashboard, etc.)
are added in later prompts.
"""

from __future__ import annotations

from fastapi import APIRouter

from payment_tracking_agent import __version__

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
