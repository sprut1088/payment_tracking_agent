"""Domain models for the local-folder demo flow (Prompt 04).

These are foundation models used by the folder scanner, scenario state store,
and API stubs. They intentionally do not parse ACH file contents — that is
deferred to a later prompt.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class FileKind(str, Enum):
    """Kind of file inferred from the folder it was discovered in."""

    CCD = "ccd"
    SETTLEMENT = "settlement"
    SCHEME_REJECT = "scheme_reject"
    RETURN = "return"


class BatchIntakeStatus(str, Enum):
    """File-evidence state for a batch tracked by the local-folder scanner.

    This is not a payment-outcome status. Return files may arrive later or
    repeatedly, so RETURN_EVIDENCE_RECEIVED does not imply the batch is
    finished or that individual payments are cleared.
    """

    AWAITING_SETTLEMENT = "AWAITING_SETTLEMENT"
    AWAITING_RETURNS = "AWAITING_RETURNS"
    RETURN_EVIDENCE_RECEIVED = "RETURN_EVIDENCE_RECEIVED"


class SettlementSchemeEvidenceStatus(str, Enum):
    """Availability of settlement and scheme-reject evidence for a batch."""

    NONE_AVAILABLE = "NONE_AVAILABLE"
    SETTLEMENT_AVAILABLE = "SETTLEMENT_AVAILABLE"
    SCHEME_REJECT_AVAILABLE = "SCHEME_REJECT_AVAILABLE"
    SETTLEMENT_AND_SCHEME_REJECT_AVAILABLE = "SETTLEMENT_AND_SCHEME_REJECT_AVAILABLE"


class DetectedFile(BaseModel):
    """A file the scanner has observed on disk."""

    model_config = ConfigDict(frozen=True)

    path: Path
    filename: str
    kind: FileKind
    size_bytes: int
    modified_at: datetime
    discovered_at: datetime


class BatchIntake(BaseModel):
    """A batch tracked from a CCD file drop.

    Correlation to settlement / scheme-reject / return files is done later by
    filename matching or ACH parsing. For this foundation prompt we only track
    the timing schedule and the discovered files that arrived after uploaded_at.
    """

    batch_id: str
    ccd_file: DetectedFile
    uploaded_at: datetime
    expected_settlement_scan_at: datetime
    expected_returns_scan_at: datetime
    status: BatchIntakeStatus = BatchIntakeStatus.AWAITING_SETTLEMENT
    settlement_scheme_status: SettlementSchemeEvidenceStatus = (
        SettlementSchemeEvidenceStatus.NONE_AVAILABLE
    )
    settlement_files: list[DetectedFile] = Field(default_factory=list)
    scheme_reject_files: list[DetectedFile] = Field(default_factory=list)
    return_files: list[DetectedFile] = Field(default_factory=list)


class ScanResult(BaseModel):
    """Result of a single folder-scan pass."""

    scanned_at: datetime
    new_files: list[DetectedFile] = Field(default_factory=list)
    new_batches: list[str] = Field(default_factory=list)
    batches_advanced: list[str] = Field(default_factory=list)


class CcdUploadOutcome(BaseModel):
    """Result of running the CCD upload pipeline on one file found during scan."""

    file_name: str
    batch_id: str
    is_valid: bool
    upload_id: str | None = None
    entry_count: int = 0
    batch_count: int = 0
    # Non-empty when is_valid=False or a read error occurred.
    errors: list[str] = Field(default_factory=list)

    # Populated when is_valid=False and corrections are available.
    # corrected_file_content is the full file text ready to accept and re-process.
    validation_error_count: int = 0
    corrected_file_content: str | None = None
    corrected_lines: list[dict] | None = None   # [{line_number, line, was_corrected}]
    is_awaiting_review: bool = False


class UnderReviewItem(BaseModel):
    """A CCD file that failed validation and is waiting for user accept/reject."""

    file_name: str
    batch_id: str
    discovered_at: str
    errors: list[str] = Field(default_factory=list)
    original_content: str
    corrected_file_content: str | None = None
    corrected_lines: list[dict] | None = None


class RejectCorrectionRequest(BaseModel):
    """Request body for the reject-correction endpoint."""

    batch_id: str
    file_name: str


class AcceptCorrectionRequest(BaseModel):
    """Request body for the accept-correction endpoint."""

    batch_id: str
    file_name: str
    # Full corrected ACH file content (value of corrected_file_content from scan-ccd).
    corrected_content: str


class ScanCCDResult(ScanResult):
    """Extended scan-ccd result: scan metadata + per-file upload outcomes."""

    uploads: list[CcdUploadOutcome] = Field(default_factory=list)


class DemoFlowState(BaseModel):
    """Aggregated snapshot of demo-flow state."""

    as_of: datetime
    batches: list[BatchIntake] = Field(default_factory=list)
    detected_files: list[DetectedFile] = Field(default_factory=list)


class DemoFlowConfigView(BaseModel):
    """Public view of the demo-flow configuration."""

    demo_flow_root: Path
    inbox_dir: Path
    settlement_dir: Path
    scheme_reject_dir: Path
    returns_dir: Path
    processed_dir: Path
    under_review_dir: Path
    settlement_delay_seconds: int
    returns_delay_seconds: int
    poll_interval_seconds: int
