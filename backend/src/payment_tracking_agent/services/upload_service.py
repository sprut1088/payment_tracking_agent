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
from payment_tracking_agent.models.payment import ParsedCCDFile as _ParsedCCDFile  # noqa: F401 (used in type hints)
from payment_tracking_agent.models.validation import (
    CorrectedLine,
    HistoricalRejectionWarning,
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
        # Even with syntax errors, attempt a best-effort parse so we can
        # run the historical rejection check on whatever records are readable.
        partial_parsed = None
        try:
            partial_parsed = ccd_parser.parse_ccd_bytes(content)
        except Exception:  # noqa: BLE001
            pass
        hist_warnings = _check_historical_rejections(partial_parsed) if partial_parsed else []
        return _build_invalid_response(file_name, original_lines, line_errors,
                                       historical_warnings=hist_warnings)

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

    # ------------------------------------------------------------------
    # Step 4: Historical rejection check
    # ------------------------------------------------------------------
    historical_warnings = _check_historical_rejections(parsed)
    if historical_warnings:
        high = sum(1 for w in historical_warnings if w.severity == "HIGH")
        medium = sum(1 for w in historical_warnings if w.severity == "MEDIUM")
        store.append_event(
            "BeforePaymentSubmissionAgent",
            f"Historical rejection check \u2014 {file_name}: "
            f"{len(historical_warnings)} warning(s) found "
            f"(HIGH={high} MEDIUM={medium}). "
            "Review before sending to scheme.",
        )

    return UploadCCDResponse(
        is_valid=True,
        file_name=file_name,
        upload_id=upload_id,
        entry_count=parsed.entry_count,
        batch_count=len(parsed.batches),
        original_lines=original_lines,
        parsed=parsed,
        historical_warnings=historical_warnings,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

# Return codes that indicate a permanent account-level problem — always HIGH.
_HIGH_SEVERITY_CODES: frozenset[str] = frozenset({
    "R02",  # Account Closed
    "R03",  # No Account / Unable to Locate Account
    "R04",  # Invalid Account Number
    "R16",  # Account Frozen
    "R20",  # Non-Transaction Account
    "R21",  # Invalid Company Identification
    "R22",  # Invalid Individual ID Number
    "R23",  # Credit Entry Refused by Receiver
    "R28",  # Routing Number Check Digit Error
})

# Return codes that indicate a recurring or compliance problem — always MEDIUM.
_MEDIUM_SEVERITY_CODES: frozenset[str] = frozenset({
    "R01",  # Insufficient Funds
    "R05",  # Unauthorized Debit
    "R07",  # Authorization Revoked
    "R08",  # Payment Stopped
    "R09",  # Uncollected Funds
    "R10",  # Customer Advises Unauthorized
    "R29",  # Corporate Customer Advises Not Authorized
    "R30",  # RDFI Not Participant in Check Truncation Program
    "R31",  # Permissible Return Entry
})


def _severity_for_code(code: str, occurrence_count: int) -> str:
    """Return severity for a return code.

    Predefined sets capture known patterns.  For any code NOT in the sets
    (including future codes we haven't anticipated), severity is escalated
    automatically based on how many times it has appeared:

      3+ occurrences → HIGH   (recurring unknown problem = treat seriously)
      2  occurrences → MEDIUM
      1  occurrence  → LOW    (isolated — could be a one-off)

    This means new NACHA return codes are handled without any code change.
    """
    if code in _HIGH_SEVERITY_CODES:
        return "HIGH"
    if code in _MEDIUM_SEVERITY_CODES:
        return "MEDIUM"
    # Unknown / future code — escalate by frequency
    if occurrence_count >= 3:
        return "HIGH"
    if occurrence_count >= 2:
        return "MEDIUM"
    return "LOW"


def _check_historical_rejections(
    parsed: _ParsedCCDFile,
) -> list[HistoricalRejectionWarning]:
    """Cross-reference every entry in *parsed* against past return/rejection records.

    For each entry, looks up all historical payments with the same vendor name
    (``individual_name``) that have a ``return_reason_code`` set.  Groups by
    return code, counts occurrences, and returns a warning for each unique
    (entry, return_code) pair that has appeared at least once before.

    Returns warnings ordered: HIGH first, then MEDIUM, then LOW.
    """
    from payment_tracking_agent.models.return_file import RETURN_REASON_DESCRIPTIONS  # noqa: PLC0415

    all_entries = store.list_all_entries()

    # Build per-vendor return history:
    # vendor_name → list of past entries that have a return_reason_code
    vendor_returns: dict[str, list] = {}
    for e in all_entries:
        if e.return_reason_code:
            key = e.individual_name.strip().lower()
            vendor_returns.setdefault(key, []).append(e)

    warnings: list[HistoricalRejectionWarning] = []

    for batch in parsed.batches:
        for entry in batch.entries:
            vendor_key = entry.individual_name.strip().lower()
            past = vendor_returns.get(vendor_key, [])
            if not past:
                continue

            # Count occurrences per return code
            code_counts: dict[str, list] = {}
            for p in past:
                code_counts.setdefault(p.return_reason_code, []).append(p)

            for code, occurrences in sorted(code_counts.items()):
                severity = _severity_for_code(code, len(occurrences))

                desc = RETURN_REASON_DESCRIPTIONS.get(code, "Unknown return reason")
                last = occurrences[-1]

                # Build a specific recommendation based on the code
                if code in {"R02", "R16"}:
                    rec = (
                        f"Account for {entry.individual_name} was previously returned "
                        f"{code} ({desc}). Verify the account is still active before submission."
                    )
                elif code in {"R03", "R04"}:
                    rec = (
                        f"Account ****{entry.dfi_account_number_masked[-4:]} for "
                        f"{entry.individual_name} returned {code} ({desc}) {len(occurrences)} "
                        "time(s). Confirm the account number and routing with the beneficiary."
                    )
                elif code == "R01":
                    rec = (
                        f"{entry.individual_name} had {len(occurrences)} insufficient-funds "
                        "return(s). Consider contacting the beneficiary before re-submission."
                    )
                else:
                    rec = (
                        f"Prior return {code} ({desc}) found for {entry.individual_name}. "
                        "Review before sending to scheme."
                    )

                warnings.append(HistoricalRejectionWarning(
                    trace_number=entry.trace_number,
                    individual_name=entry.individual_name,
                    account_masked=entry.dfi_account_number_masked,
                    receiving_dfi=entry.receiving_dfi,
                    return_code=code,
                    return_description=desc,
                    occurrence_count=len(occurrences),
                    last_seen_trace=last.trace_number,
                    severity=severity,
                    recommendation=rec,
                ))

    # Sort: HIGH first, then MEDIUM, then LOW; within tier by occurrence count desc
    _sev_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    warnings.sort(key=lambda w: (_sev_order.get(w.severity, 9), -w.occurrence_count))
    return warnings


def _build_invalid_response(
    file_name: str,
    original_lines: list[str],
    line_errors: list,
    historical_warnings: list[HistoricalRejectionWarning] | None = None,
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
        historical_warnings=historical_warnings or [],
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
