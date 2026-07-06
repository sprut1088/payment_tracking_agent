"""Models for pre-submission batch risk validation.

Every CCD upload is validated against the in-memory payment history before
payments are pushed to the scheme.  Results are stored per upload_id so the
Batch Dashboard and API can surface them.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PaymentRiskAssessment(BaseModel):
    """Risk assessment for one payment entry before scheme submission."""

    trace_number: str
    customer_id: str
    customer_name: str
    amount: float
    receiving_dfi: str
    account_masked: str

    # Deterministic risk engine output
    risk_level: str                   # LOW / MEDIUM / HIGH
    risk_reason: str

    # Historical signals
    historical_total_payments: int
    historical_rejections: int
    historical_returns: int
    rejection_rate_pct: float
    rejections_last_30d: int

    # AI-driven recommendation
    action: str                       # PROCEED / REVIEW / HOLD
    ai_recommendation: str            # 2-3 sentences


class CustomerRiskSummary(BaseModel):
    """Aggregated risk view per customer across all their payments in the batch."""

    customer_id: str
    customer_name: str
    payment_count: int
    total_amount: float
    risk_level: str
    risk_reason: str
    action: str                       # worst action across their payments
    ai_recommendation: str
    trace_numbers: list[str]


class BatchPreSubmissionResult(BaseModel):
    """Full pre-submission validation result for one CCD upload."""

    upload_id: str
    file_name: str
    validated_at: datetime

    # Batch-level risk (highest across all payments)
    batch_risk_level: str
    batch_risk_reason: str

    # Counts
    total_payments: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    hold_count: int          # AI recommended HOLD
    review_count: int        # AI recommended REVIEW
    proceed_count: int       # AI recommended PROCEED

    # Detail
    payment_assessments: list[PaymentRiskAssessment]
    customer_summaries: list[CustomerRiskSummary]

    # Overall AI summary for the whole batch
    ai_batch_summary: str
