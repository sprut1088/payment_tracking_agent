"""Service layer for CCD file upload processing.

Routes delegate here. This module owns the full validate → LLM-fix → parse → save
pipeline so the HTTP layer stays thin.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from payment_tracking_agent.agents import llm_fixer
from payment_tracking_agent.config import settings
from payment_tracking_agent.ledger import store
from payment_tracking_agent.validators import nacha_reconstructor
from payment_tracking_agent.models.payment import UploadRecord
from payment_tracking_agent.models.validation import (
    CorrectedLine,
    LineValidationError,
    LLMFixSuggestion,
    UploadCCDResponse,
)
from payment_tracking_agent.parsers import ccd as ccd_parser
from payment_tracking_agent.validators import ccd_validator

_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".ach", ".txt", ".dat", ""})
_MAX_FILE_BYTES: int = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class UploadValidationError(ValueError):
    """Raised for HTTP-400-class problems (bad extension, empty file, too large)."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def validate_upload_preconditions(file_name: str, content: bytes) -> None:
    """Check HTTP-level preconditions before touching the file content.

    Raises:
        UploadValidationError: with an appropriate ``status_code``.
    """
    suffix = Path(file_name).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise UploadValidationError(
            f"Unsupported file extension '{suffix}'. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
            status_code=400,
        )
    if len(content) == 0:
        raise UploadValidationError("Uploaded file is empty.", status_code=400)
    if len(content) > _MAX_FILE_BYTES:
        raise UploadValidationError(
            "File exceeds the maximum allowed size of 10 MB.", status_code=413
        )


def process_ccd_upload(file_name: str, content: bytes) -> UploadCCDResponse:
    """Run the full upload pipeline and return a unified response.

    Pipeline:
      1. Decode and split into lines.
      2. Syntax-validate every NACHA record (types 1 / 5 / 6).
      3. If errors → call LLM for batched fix suggestions → return invalid response.
      4. If clean → parse entry details → save to disk and in-memory store
                  → return valid response.

    Args:
        file_name: Original filename from the multipart upload.
        content:   Raw bytes of the uploaded file.

    Returns:
        ``UploadCCDResponse`` with ``is_valid=True`` (file saved) or
        ``is_valid=False`` (errors + suggestions, file not saved).
    """
    raw_text = content.decode("ascii", errors="replace")
    # Strip trailing commas that appear when files are saved from Excel/CSV tools
    original_lines = [ln.rstrip(",") for ln in raw_text.splitlines()]

    # ------------------------------------------------------------------
    # Step 1: Syntax validation
    # ------------------------------------------------------------------
    line_errors = ccd_validator.validate_lines(raw_text)

    if line_errors:
        return _build_invalid_response(file_name, original_lines, line_errors)

    # ------------------------------------------------------------------
    # Step 2: Parse entry detail records
    # ------------------------------------------------------------------
    parsed = ccd_parser.parse_ccd_bytes(content)

    # ------------------------------------------------------------------
    # Step 3: Persist — disk then in-memory store
    # ------------------------------------------------------------------
    upload_id = _save_to_disk(file_name, content)
    record = UploadRecord(
        upload_id=upload_id,
        file_name=file_name,
        file_path=str(_upload_path(upload_id, file_name)),
        uploaded_at=datetime.now(tz=timezone.utc),
        entry_count=parsed.entry_count,
        batch_count=len(parsed.batches),
        parsed=parsed,
    )
    store.save_upload(record)

    store.append_event(
        "BeforePaymentSubmissionAgent",
        f"CCD uploaded \u2014 {file_name}: {parsed.entry_count} payment(s) parsed across "
        f"{len(parsed.batches)} batch(es). Status: WITH BANK.",
    )

    return UploadCCDResponse(
        is_valid=True,
        file_name=file_name,
        upload_id=upload_id,
        entry_count=parsed.entry_count,
        batch_count=len(parsed.batches),
        original_lines=original_lines,
        parsed=parsed,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_invalid_response(
    file_name: str,
    original_lines: list[str],
    line_errors: list,
) -> UploadCCDResponse:
    """Build the error response: group errors by line, call LLM, build corrected file."""
    # Group by line so we send one batched LLM request
    error_by_line: dict[int, list] = {}
    for err in line_errors:
        error_by_line.setdefault(err.line_number, []).append(err)

    errored_lines = [
        (ln, original_lines[ln - 1], errs)
        for ln, errs in sorted(error_by_line.items())
    ]

    raw_suggestions = llm_fixer.suggest_fixes(errored_lines)

    # Build a lookup of what the LLM produced, keyed by line number.
    original_line_map: dict[int, str] = {ln: raw for ln, raw, _ in errored_lines}
    llm_by_line: dict[int, dict] = {
        s["line_number"]: s
        for s in raw_suggestions
        if s.get("corrected_line")
    }

    # For every errored line, use the LLM correction only when it produced
    # exactly 94 chars.  Otherwise fall back to the deterministic reconstructor
    # which guarantees the correct length.
    suggestion_map: dict[int, str] = {}
    explanation_map: dict[int, str] = {}
    final_suggestions: list[dict] = []
    for ln, raw_line, _ in errored_lines:
        llm_entry = llm_by_line.get(ln)
        if llm_entry and len(llm_entry["corrected_line"]) == 94:
            suggestion_map[ln] = llm_entry["corrected_line"]
            explanation_map[ln] = llm_entry.get("explanation", "")
            final_suggestions.append(llm_entry)
        else:
            reconstructed = nacha_reconstructor.reconstruct_record(raw_line)
            suggestion_map[ln] = reconstructed
            note = " [length corrected deterministically]" if llm_entry else " [reconstructed deterministically — LLM unavailable or failed]"
            expl = (llm_entry["explanation"] + note) if llm_entry else note.strip()
            explanation_map[ln] = expl
            final_suggestions.append({
                "line_number": ln,
                "original_line": raw_line,
                "corrected_line": reconstructed,
                "explanation": expl,
            })

    # Only build corrected_lines when the LLM actually provided fixes.
    # When suggestion_map is empty (no LLM key or no fixes), return None so
    # callers don't mistake a copy of original_lines for real corrections.
    if suggestion_map:
        corrected_lines: list[CorrectedLine] | None = [
            CorrectedLine(
                line_number=i + 1,
                line=suggestion_map.get(i + 1, line),
                was_corrected=(i + 1) in suggestion_map,
                explanation=explanation_map.get(i + 1) if (i + 1) in suggestion_map else None,
            )
            for i, line in enumerate(original_lines)
        ]
        # Use \r\n (NACHA standard) so the content can be saved directly to a
        # .ach file and re-uploaded without modification.
        corrected_file_content: str | None = "\r\n".join(
            suggestion_map.get(i + 1, line) for i, line in enumerate(original_lines)
        ) + "\r\n"
    else:
        corrected_lines = None
        corrected_file_content = None

    return UploadCCDResponse(
        is_valid=False,
        file_name=file_name,
        entry_count=0,
        batch_count=0,
        validation_errors=[
            LineValidationError(
                line_number=e.line_number,
                record_type=e.record_type,
                field=e.field,
                issue=e.issue,
                raw_line=e.raw_line,
            )
            for e in line_errors
        ],
        llm_suggestions=[
            LLMFixSuggestion(
                line_number=s["line_number"],
                original_line=s["original_line"],
                corrected_line=s["corrected_line"],
                explanation=s["explanation"],
            )
            for s in final_suggestions
        ],
        original_lines=original_lines,
        corrected_lines=corrected_lines,
        corrected_file_content=corrected_file_content,
    )


def _upload_path(upload_id: str, file_name: str) -> Path:
    return Path(settings.upload_dir) / f"{upload_id}_{Path(file_name).name}"


def _save_to_disk(file_name: str, content: bytes) -> str:
    """Write raw bytes to the upload directory and return the new upload_id."""
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_id = str(uuid.uuid4())
    _upload_path(upload_id, file_name).write_bytes(content)
    return upload_id
