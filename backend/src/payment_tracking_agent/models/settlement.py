"""Models for settlement rejection file processing."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FedAchSummary(BaseModel):
    """Metadata extracted from a FedACH-style fixed-width summary file.

    Populated when the settlement file uses the 10/20/30 record format
    instead of pipe-delimited rejection records.
    """

    settlement_date: str = ""       # YYYYMMDD from record type 10
    settlement_time: str = ""       # HHMMSS from record type 10
    routing_number: str = ""        # 8-char routing from record type 10
    description: str = ""           # free text from record type 10
    category: str = ""              # 4-char category code from record type 20
    item_count: int = 0             # total items (from record type 30 when available)
    gross_amount_cents: int = 0     # settlement amount in cents from record type 20
    net_indicator: str = "C"        # C = credit, D = debit from record type 20

    @property
    def gross_amount_dollars(self) -> float:
        return round(self.gross_amount_cents / 100.0, 2)

    @property
    def settlement_datetime_display(self) -> str:
        d = self.settlement_date
        t = self.settlement_time
        if len(d) == 8 and len(t) >= 4:
            return f"{d[0:4]}-{d[4:6]}-{d[6:8]} {t[0:2]}:{t[2:4]}"
        return f"{d} {t}".strip()



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
    # Populated when the file is a FedACH summary (10/20/30 fixed-width format)
    fed_ach_summary: FedAchSummary | None = None
