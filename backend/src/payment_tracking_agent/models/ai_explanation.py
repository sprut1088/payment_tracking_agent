"""Response models for the AI payment explanation endpoint."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AIExplanationResponse(BaseModel):
    """Structured explanation returned by the Anthropic Claude layer.

    The AI explains deterministic evidence only. It never determines or
    changes payment status.
    """

    payment_id: str
    provider: str = "anthropic"
    model: str
    summary: str
    status_explanation: str
    evidence_used: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommended_action: str
    customer_safe_message: str
    generated_at: datetime
