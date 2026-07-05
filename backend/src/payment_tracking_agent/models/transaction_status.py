"""Response models for transaction-status query endpoints."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class TransactionStatus(BaseModel):
    """Current status snapshot for a single ACH entry detail record."""

    trace_number: str
    batch_number: str
    sec_code: str
    transaction_code: str
    receiving_dfi: str
    check_digit: str
    dfi_account_number_masked: str
    individual_id_number: str
    individual_name: str
    amount: float
    amount_cents: int
    addenda_indicator: str

    # Lifecycle
    status: str
    business_status: str
    corrective_action: str | None = None
    return_reason_code: str | None = None
    return_reason_description: str | None = None
    return_customer_message: str | None = None
    risk_level: str = "LOW"
    risk_reason: str | None = None


class FileTransactionsResponse(BaseModel):
    """File metadata + every transaction's current status."""

    upload_id: str
    file_name: str
    uploaded_at: datetime
    entry_count: int
    batch_count: int

    # File-level metadata
    immediate_destination: str
    immediate_origin: str
    file_creation_date: str
    file_creation_time: str
    immediate_destination_name: str
    immediate_origin_name: str

    # Status summary counts
    summary: dict[str, int]        # business_status → count

    transactions: list[TransactionStatus]


class PaymentListItem(BaseModel):
    """One row in the flat all-payments list."""

    upload_id: str
    file_name: str
    uploaded_at: datetime

    trace_number: str
    batch_number: str
    individual_name: str
    individual_id_number: str
    amount: float
    amount_cents: int
    receiving_dfi: str
    dfi_account_number_masked: str

    status: str
    business_status: str
    corrective_action: str | None = None
    return_reason_code: str | None = None
    return_reason_description: str | None = None
    return_customer_message: str | None = None
    risk_level: str = "LOW"
    risk_reason: str | None = None


class CustomerSummaryItem(BaseModel):
    """Aggregated customer view — one row per unique individual_id_number."""

    customer_id: str
    customer_name: str
    total_payments: int
    with_bank: int
    sent_to_scheme: int
    with_beneficiary_bank: int
    rejected_by_scheme: int
    rejected_by_beneficiary_bank: int
    last_rejection_date: str | None = None
    historical_rejection_count: int
    risk_level: str = "LOW"
    risk_reason: str | None = None
