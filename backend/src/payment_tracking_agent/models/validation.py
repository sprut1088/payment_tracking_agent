"""Response models for the CCD upload + validation endpoint."""

from __future__ import annotations

from pydantic import BaseModel

from payment_tracking_agent.models.payment import ParsedCCDFile


class LineValidationError(BaseModel):
    """A single field-level syntax error found in the uploaded file."""

    line_number: int
    record_type: str
    field: str
    issue: str
    raw_line: str


class LLMFixSuggestion(BaseModel):
    """LLM-suggested correction for one errored line."""

    line_number: int
    original_line: str
    corrected_line: str
    explanation: str


class CorrectedLine(BaseModel):
    """One line of the file after corrections are applied."""

    line_number: int
    line: str
    was_corrected: bool = False
    explanation: str | None = None  # LLM-generated plain-English description of the change


class HistoricalRejectionWarning(BaseModel):
    """A warning derived from past return/rejection history for a payment entry.

    Generated deterministically at upload time — before the file is sent to
    the scheme — so operators can fix issues before submission.
    """

    trace_number: str          # trace number of the entry being flagged
    individual_name: str       # vendor / beneficiary name
    account_masked: str        # masked account number of the current entry
    receiving_dfi: str         # routing of the current entry

    return_code: str           # most recent past return code (e.g. R02)
    return_description: str    # human-readable NACHA description
    occurrence_count: int      # how many times this return was seen historically
    last_seen_trace: str       # trace number of the most recent prior return
    severity: str              # "HIGH" | "MEDIUM" | "LOW"
    recommendation: str        # deterministic recommendation text


class UploadCCDResponse(BaseModel):
    """Unified response for the CCD upload endpoint.

    - ``is_valid=True``  → file passed all syntax checks; saved to DB and disk.
    - ``is_valid=False`` → syntax errors found; not saved; LLM suggestions provided.
    """

    is_valid: bool
    file_name: str

    # Set only when is_valid=True (file was saved)
    upload_id: str | None = None

    entry_count: int
    batch_count: int

    # Populated when is_valid=False
    validation_errors: list[LineValidationError] = []
    llm_suggestions: list[LLMFixSuggestion] = []

    # Always present — the raw lines exactly as uploaded
    original_lines: list[str] = []

    # Present when is_valid=False and LLM provided corrections.
    # Each entry carries its line_number and a flag indicating whether it was changed.
    corrected_lines: list[CorrectedLine] | None = None

    # Present when is_valid=False and LLM provided corrections.
    # The full reconstructed file content with all corrected lines applied, ready to re-upload.
    corrected_file_content: str | None = None

    # Present when is_valid=True
    parsed: ParsedCCDFile | None = None

    # Populated when is_valid=True and historical rejections are found for any entry.
    # These are deterministic warnings based on past return/rejection data — generated
    # at upload time so operators can fix issues before the batch is sent to scheme.
    historical_warnings: list[HistoricalRejectionWarning] = []
