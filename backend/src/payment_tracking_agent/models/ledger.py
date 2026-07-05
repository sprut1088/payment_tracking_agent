"""Payment ledger domain models (Prompt 09).

Business statuses come from ``.github/copilot-instructions.md``. Only the
statuses reachable in this prompt are populated by backend code today
(``SENT TO SCHEME`` and ``WITH BANK``); the rest are declared so downstream
prompts can update payments without changing the enum.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from payment_tracking_agent.models.ai_risk import (
    BatchRiskClassification,
    CustomerRiskClassification,
    RiskClassification,
)


class PaymentStatus(str, Enum):
    """SME-confirmed business-facing payment statuses."""

    WITH_BANK = "WITH BANK"
    SENT_TO_SCHEME = "SENT TO SCHEME"
    WITH_BENEFICIARY_BANK = "WITH BENEFICIARY BANK"
    REJECTED_BY_SCHEME = "REJECTED BY SCHEME"
    REJECTED_BY_BENEFICIARY_BANK = "REJECTED BY BENEFICIARY BANK"


class PaymentEvidence(BaseModel):
    """Grounded explanation for a payment status change."""

    source: str
    summary: str
    recorded_at: datetime


class PaymentStatusEvent(BaseModel):
    """One entry in a payment's status history."""

    status: PaymentStatus
    at: datetime
    evidence: PaymentEvidence


class Payment(BaseModel):
    """A tracked ACH payment created from a CCD entry detail row."""

    payment_id: str
    batch_key: str
    source_file: str
    trace_number: str
    transaction_code: str
    receiving_dfi_identification: str
    masked_account_number: str
    amount_cents: int
    individual_id_number: str
    individual_name: str
    current_status: PaymentStatus
    status_history: list[PaymentStatusEvent] = Field(default_factory=list)
    evidence: list[PaymentEvidence] = Field(default_factory=list)
    current_risk_classification: RiskClassification | None = None
    risk_classification_history: list[RiskClassification] = Field(default_factory=list)
    current_customer_risk_classification: CustomerRiskClassification | None = None
    customer_risk_classification_history: list[CustomerRiskClassification] = Field(
        default_factory=list
    )
    current_batch_risk_classification: BatchRiskClassification | None = None
    batch_risk_classification_history: list[BatchRiskClassification] = Field(
        default_factory=list
    )


class PaymentLedgerView(BaseModel):
    """Public snapshot of the in-memory payment ledger."""

    as_of: datetime
    payments: list[Payment] = Field(default_factory=list)
