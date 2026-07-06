"""Domain models for ACH CCD file upload and payment records."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class PaymentStatus(str, Enum):
    """Internal sub-statuses for the ACH payment lifecycle.

    Each sub-status rolls up to one of the five business-facing statuses:
      WITH BANK            → WITH_BANK_*
      WITH SCHEME          → WITH_SCHEME_*
      WITH BENEFICIARY BANK → WITH_BENEFICIARY_BANK_*
      CLEARED              → CLEARED_*
      REJECTED             → REJECTED_*
    """

    # --- WITH BANK ---
    WITH_BANK_NOT_UPLOADED = "WITH_BANK_NOT_UPLOADED"
    WITH_BANK_UPLOADED = "WITH_BANK_UPLOADED"          # initial status after upload
    WITH_BANK_VALIDATING = "WITH_BANK_VALIDATING"
    WITH_BANK_VALIDATION_FAILED = "WITH_BANK_VALIDATION_FAILED"
    WITH_BANK_READY_FOR_SCHEME = "WITH_BANK_READY_FOR_SCHEME"

    # --- WITH SCHEME ---
    WITH_SCHEME_SUBMITTED = "WITH_SCHEME_SUBMITTED"
    WITH_SCHEME_ACKNOWLEDGED = "WITH_SCHEME_ACKNOWLEDGED"

    # --- WITH BENEFICIARY BANK ---
    WITH_BENEFICIARY_BANK_PENDING = "WITH_BENEFICIARY_BANK_PENDING"

    # --- CLEARED ---
    CLEARED_BY_SETTLEMENT = "CLEARED_BY_SETTLEMENT"

    # --- REJECTED ---
    REJECTED_BY_RETURN_FILE = "REJECTED_BY_RETURN_FILE"
    REJECTED_BY_SETTLEMENT = "REJECTED_BY_SETTLEMENT"

    # --- EXCEPTIONS ---
    RECONCILIATION_EXCEPTION = "RECONCILIATION_EXCEPTION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"

    @property
    def business_status(self) -> str:
        """Return the user-facing business status for this sub-status."""
        _map = {
            "WITH_BANK": "WITH BANK",
            "WITH_SCHEME": "WITH SCHEME",
            "WITH_BENEFICIARY_BANK": "WITH BENEFICIARY BANK",
            "CLEARED": "CLEARED",
            "REJECTED": "REJECTED",
            "RECONCILIATION": "WITH BANK",
            "REVIEW": "WITH BANK",
        }
        for prefix, label in _map.items():
            if self.value.startswith(prefix):
                return label
        return self.value


class FileHeaderRecord(BaseModel):
    """Parsed ACH file header (record type 1)."""

    immediate_destination: str
    immediate_origin: str
    file_creation_date: str
    file_creation_time: str
    file_id_modifier: str
    immediate_destination_name: str
    immediate_origin_name: str


class BatchHeaderRecord(BaseModel):
    """Parsed ACH batch header (record type 5)."""

    service_class_code: str
    company_name: str
    company_identification: str
    sec_code: str
    company_entry_description: str
    effective_entry_date: str
    odfi_identification: str
    batch_number: str


class EntryDetailRecord(BaseModel):
    """Parsed ACH entry detail (record type 6) — one per payment."""

    transaction_code: str
    receiving_dfi: str
    check_digit: str
    dfi_account_number_masked: str
    amount_cents: int
    amount: float
    individual_id_number: str
    individual_name: str            # beneficiary / counterparty (Entry Detail type 6)
    # Originator fields — copied from the enclosing Batch Header (type 5)
    company_name: str = ""          # originating company — the bank's customer
    company_identification: str = "" # 10-char company ID from Batch Header
    trace_number: str
    addenda_indicator: str
    batch_number: str
    sec_code: str
    # Lifecycle status — set to WITH_BANK_UPLOADED as soon as the file passes
    # validation and is saved; advances through the ACH lifecycle from here.
    status: PaymentStatus = PaymentStatus.WITH_BANK_UPLOADED
    business_status: str = PaymentStatus.WITH_BANK_UPLOADED.business_status
    # LLM-generated corrective action — populated when a settlement rejection is processed
    corrective_action: str | None = None
    # Return file evidence — populated when a NACHA return is matched to this entry
    return_reason_code: str | None = None
    return_reason_description: str | None = None
    return_customer_message: str | None = None


class ParsedBatch(BaseModel):
    """One ACH batch containing its header and entry detail records."""

    header: BatchHeaderRecord
    entries: list[EntryDetailRecord]


class ParsedCCDFile(BaseModel):
    """Full parsed result of a CCD upload file."""

    file_header: FileHeaderRecord
    batches: list[ParsedBatch]
    entry_count: int


class UploadRecord(BaseModel):
    """Persisted record of a CCD file upload (stored in temp DB)."""

    upload_id: str
    file_name: str
    file_path: str
    uploaded_at: datetime
    entry_count: int
    batch_count: int
    parsed: ParsedCCDFile
