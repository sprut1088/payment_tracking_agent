"""Models for settlement rejection file processing."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RejectionRecord(BaseModel):
    """One rejected payment entry parsed from a settlement file."""

    trace_number: str
    reason_code: str
    reason_text: str
    # Populated by the LLM advisor after processing
    llm_suggested_action: str = ""
    # Populated when the trace was matched to a stored payment
    matched_upload_id: str | None = None
    matched: bool = False


class ProcessedSettlementFile(BaseModel):
    """Result of processing a settlement rejection file."""

    settlement_file_id: str
    file_name: str
    file_path: str
    processed_at: datetime
    rejection_records: list[RejectionRecord]
    matched_count: int
    unmatched_count: int
    # Unique reason codes seen in this file — useful for audit / dashboard
    reason_codes_seen: list[str] = []
