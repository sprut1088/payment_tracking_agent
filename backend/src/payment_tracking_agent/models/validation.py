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
