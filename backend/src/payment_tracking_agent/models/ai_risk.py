"""AI payment / customer / batch risk classification models.

Three classification kinds live in this module:

- :class:`RiskClassification` — per-payment classification stamped at
  lifecycle triggers (``CCD_UPLOAD``, ``SETTLEMENT_OR_SCHEME_REJECT``,
  ``NACHA_RETURN``). At CCD upload the classification reflects **customer
  history and batch validation quality**, not the fact that the payment is
  merely ``SENT TO SCHEME`` with no downstream evidence yet.
- :class:`CustomerRiskClassification` — per-customer classification based
  on historical rejection trend only.
- :class:`BatchRiskClassification` — per-batch classification based on
  CCD syntax/validation findings only.

Design rules:

- The AI never determines payment status.
- Deterministic ledger status remains authoritative.
- ``clearing_confidence`` is *AI operational confidence only*. It is
  never payment-level clearing evidence.
- Do not classify credit risk. Do not classify fraud risk.
- Do not add database persistence yet.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RiskBand(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ClearingConfidence(str, Enum):
    """AI operational confidence only. Not payment-level clearing evidence."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskClassificationTrigger(str, Enum):
    """Lifecycle event that caused a payment classification to be stamped."""

    CCD_UPLOAD = "CCD_UPLOAD"
    SETTLEMENT_OR_SCHEME_REJECT = "SETTLEMENT_OR_SCHEME_REJECT"
    NACHA_RETURN = "NACHA_RETURN"


class OutcomeAlignment(str, Enum):
    """How a prior CCD_UPLOAD prediction lines up with the actual return outcome."""

    RISK_RAISED_BEFORE_REJECTION = "RISK_RAISED_BEFORE_REJECTION"
    UNEXPECTED_REJECTION = "UNEXPECTED_REJECTION"
    EXPECTED_REJECTION = "EXPECTED_REJECTION"
    NOT_APPLICABLE = "NOT_APPLICABLE"


CLEARING_CONFIDENCE_NOTE = (
    "AI operational confidence only. Not payment-level clearing evidence."
)


class PriorPredictionOutcome(BaseModel):
    """Prior-prediction vs actual-outcome comparison for NACHA return.

    Populated by :class:`RiskClassification` only for the ``NACHA_RETURN``
    trigger. Never claims payment-level clearing evidence.
    """

    prior_risk_score: int | None = Field(default=None, ge=0, le=100)
    prior_risk_band: RiskBand | None = None
    prior_clearing_confidence: ClearingConfidence | None = None
    actual_outcome_status: str
    outcome_alignment: OutcomeAlignment
    narrative: str


class RiskClassification(BaseModel):
    """Per-payment risk classification stamp.

    - CCD_UPLOAD uses customer history + batch validation.
    - SETTLEMENT_OR_SCHEME_REJECT uses actual settlement / scheme evidence.
    - NACHA_RETURN captures actual adverse outcome and prior-prediction
      alignment via ``prior_prediction``.
    """

    trigger: RiskClassificationTrigger
    risk_score: int = Field(ge=0, le=100)
    risk_band: RiskBand
    clearing_confidence: ClearingConfidence
    clearing_confidence_note: str = CLEARING_CONFIDENCE_NOTE
    summary: str
    risk_drivers: list[str] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)
    recommendation: str
    prior_prediction: PriorPredictionOutcome | None = None
    provider: str
    model: str
    classified_at: datetime


class CustomerRiskClassification(BaseModel):
    """Per-customer risk classification based on historical rejection trend."""

    customer_id: str
    customer_name: str
    risk_score: int = Field(ge=0, le=100)
    risk_band: RiskBand
    confidence_score: int = Field(ge=0, le=100)
    classification_trigger: str = "CUSTOMER_HISTORY"
    summary: str
    risk_drivers: list[str] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommendation: str
    classified_at: datetime
    provider: str
    model: str


class BatchRiskClassification(BaseModel):
    """Per-batch risk classification based on CCD syntax/validation findings."""

    batch_key: str
    source_file: str
    risk_score: int = Field(ge=0, le=100)
    risk_band: RiskBand
    confidence_score: int = Field(ge=0, le=100)
    classification_trigger: str = "CCD_VALIDATION"
    summary: str
    risk_drivers: list[str] = Field(default_factory=list)
    validation_findings: list[str] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommendation: str
    classified_at: datetime
    provider: str
    model: str
