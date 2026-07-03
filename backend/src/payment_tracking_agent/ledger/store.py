"""In-memory upload store — acts as the temp DB for the PoC.

All uploaded CCD files, their parsed records, and processed return files are
held in module-level dicts for the lifetime of the process.
The ``clear()`` function resets all state for tests.
"""

from __future__ import annotations

from datetime import datetime, timezone

from payment_tracking_agent.models.payment import EntryDetailRecord, PaymentStatus, UploadRecord
from payment_tracking_agent.models.return_file import ProcessedReturnFile
from payment_tracking_agent.models.settlement import ProcessedSettlementFile

_MAX_EVENTS = 200  # cap so memory doesn't grow unbounded

# ---------------------------------------------------------------------------
# Upload store
# ---------------------------------------------------------------------------

_uploads: dict[str, UploadRecord] = {}


def save_upload(record: UploadRecord) -> None:
    """Persist an upload record keyed by its upload_id."""
    _uploads[record.upload_id] = record


def get_upload(upload_id: str) -> UploadRecord | None:
    return _uploads.get(upload_id)


def list_uploads() -> list[UploadRecord]:
    """Return all upload records, newest first."""
    return sorted(_uploads.values(), key=lambda r: r.uploaded_at, reverse=True)


def list_all_entries() -> list[EntryDetailRecord]:
    """Return every EntryDetailRecord across all uploads (any order).

    Used by the risk engine so it can compute per-customer rejection rates
    over the full available payment history without re-iterating uploads.
    """
    entries: list[EntryDetailRecord] = []
    for record in _uploads.values():
        for batch in record.parsed.batches:
            entries.extend(batch.entries)
    return entries


def list_all_entries_with_timestamps() -> list[tuple[EntryDetailRecord, datetime]]:
    """Return every EntryDetailRecord paired with its upload timestamp.

    The upload ``uploaded_at`` is the best available proxy for when the
    payment event occurred.  Used by the time-aware risk engine.
    """
    pairs: list[tuple[EntryDetailRecord, datetime]] = []
    for record in _uploads.values():
        for batch in record.parsed.batches:
            for entry in batch.entries:
                pairs.append((entry, record.uploaded_at))
    return pairs


# ---------------------------------------------------------------------------
# Payment lookup & status mutation
# ---------------------------------------------------------------------------

def find_payment_by_trace(
    trace_number: str,
) -> tuple[UploadRecord | None, EntryDetailRecord | None]:
    """Search all uploads for the entry whose trace number matches.

    Returns:
        ``(upload_record, entry_record)`` if found, ``(None, None)`` otherwise.
    """
    for record in _uploads.values():
        for batch in record.parsed.batches:
            for entry in batch.entries:
                if entry.trace_number == trace_number:
                    return record, entry
    return None, None


def update_payment_status(
    upload_id: str,
    trace_number: str,
    new_status: PaymentStatus,
) -> bool:
    """Update the status of a single payment identified by upload_id + trace_number.

    Returns ``True`` if the entry was found and updated.
    """
    record = _uploads.get(upload_id)
    if not record:
        return False
    for batch in record.parsed.batches:
        for entry in batch.entries:
            if entry.trace_number == trace_number:
                entry.status = new_status
                entry.business_status = new_status.business_status
                return True
    return False


def update_payment_return_info(
    upload_id: str,
    trace_number: str,
    return_reason_code: str,
    return_reason_description: str,
    customer_message: str,
    corrective_action: str,
) -> bool:
    """Store NACHA return evidence on a matched payment entry.

    Should be called after ``update_payment_status`` for return-file matches.
    Returns ``True`` if the entry was found and updated.
    """
    record = _uploads.get(upload_id)
    if not record:
        return False
    for batch in record.parsed.batches:
        for entry in batch.entries:
            if entry.trace_number == trace_number:
                entry.return_reason_code = return_reason_code
                entry.return_reason_description = return_reason_description
                entry.return_customer_message = customer_message
                entry.corrective_action = corrective_action
                return True
    return False


def update_all_payments_status(upload_id: str, new_status: PaymentStatus) -> None:
    """Advance every payment in an upload to *new_status*."""
    record = _uploads.get(upload_id)
    if not record:
        return
    for batch in record.parsed.batches:
        for entry in batch.entries:
            entry.status = new_status
            entry.business_status = new_status.business_status


def advance_submitted_to_beneficiary_bank() -> int:
    """Advance all WITH_SCHEME_SUBMITTED payments to WITH_BENEFICIARY_BANK_PENDING.

    Only moves payments that are currently WITH_SCHEME_SUBMITTED; any already-
    rejected or further-advanced payments are left untouched.

    Returns:
        Count of payments advanced.
    """
    advanced = 0
    for record in _uploads.values():
        for batch in record.parsed.batches:
            for entry in batch.entries:
                if entry.status == PaymentStatus.WITH_SCHEME_SUBMITTED:
                    entry.status = PaymentStatus.WITH_BENEFICIARY_BANK_PENDING
                    entry.business_status = PaymentStatus.WITH_BENEFICIARY_BANK_PENDING.business_status
                    advanced += 1
    return advanced


def set_payment_corrective_action(
    upload_id: str,
    trace_number: str,
    action: str,
) -> bool:
    """Attach an LLM corrective action string to a specific payment entry.

    Returns ``True`` if the entry was found and updated.
    """
    record = _uploads.get(upload_id)
    if not record:
        return False
    for batch in record.parsed.batches:
        for entry in batch.entries:
            if entry.trace_number == trace_number:
                entry.corrective_action = action
                return True
    return False


# ---------------------------------------------------------------------------
# Return file store
# ---------------------------------------------------------------------------

_return_files: dict[str, ProcessedReturnFile] = {}


def save_return_file(record: ProcessedReturnFile) -> None:
    _return_files[record.return_file_id] = record


def get_return_file(return_file_id: str) -> ProcessedReturnFile | None:
    return _return_files.get(return_file_id)


def list_return_files() -> list[ProcessedReturnFile]:
    """Return all processed return files, newest first."""
    return sorted(_return_files.values(), key=lambda r: r.processed_at, reverse=True)


# ---------------------------------------------------------------------------
# Settlement file store
# ---------------------------------------------------------------------------

_settlement_files: dict[str, ProcessedSettlementFile] = {}


def save_settlement_file(record: ProcessedSettlementFile) -> None:
    _settlement_files[record.settlement_file_id] = record


def get_settlement_file(settlement_file_id: str) -> ProcessedSettlementFile | None:
    return _settlement_files.get(settlement_file_id)


def list_settlement_files() -> list[ProcessedSettlementFile]:
    """Return all processed settlement files, newest first."""
    return sorted(
        _settlement_files.values(), key=lambda r: r.processed_at, reverse=True
    )


# ---------------------------------------------------------------------------
# Drop folder processing log
# ---------------------------------------------------------------------------
# Each entry is a plain dict with keys:
#   filename, file_type ("ccd"|"settlement"|"returns"),
#   outcome ("processed"|"error"|"under-review"),
#   processed_at (ISO-8601), size_bytes (int), detail (str|None)

_drop_file_log: list[dict] = []
_MAX_DROP_LOG = 500


def record_drop_file(
    filename: str,
    file_type: str,
    outcome: str,
    size_bytes: int,
    detail: str | None = None,
) -> None:
    """Record that the scheduler processed a file from a drop/ input folder."""
    _drop_file_log.append({
        "filename": filename,
        "file_type": file_type,
        "outcome": outcome,
        "processed_at": datetime.now(tz=timezone.utc).isoformat(),
        "size_bytes": size_bytes,
        "detail": detail,
    })
    if len(_drop_file_log) > _MAX_DROP_LOG:
        del _drop_file_log[0]


def list_drop_files() -> list[dict]:
    """Return all recorded drop-file processing events, newest first."""
    return list(reversed(_drop_file_log))


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def clear() -> None:
    """Remove all records (used in tests)."""
    from payment_tracking_agent.risk.engine import invalidate_risk_cache  # noqa: PLC0415
    _uploads.clear()
    _return_files.clear()
    _settlement_files.clear()
    _events.clear()
    _drop_file_log.clear()
    invalidate_risk_cache()


# ---------------------------------------------------------------------------
# System event log
# ---------------------------------------------------------------------------

_events: list[dict] = []


def append_event(agent: str, message: str) -> None:
    """Append a system event to the in-memory log.

    Keeps at most ``_MAX_EVENTS`` entries (drops the oldest when full).
    Uses local system time so the timestamp matches the UI display.
    """
    _events.append({
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "cycleTime": "",
        "agent": agent,
        "message": message,
    })
    if len(_events) > _MAX_EVENTS:
        del _events[0]


def list_events(limit: int = _MAX_EVENTS) -> list[dict]:
    """Return the most recent *limit* events, newest first."""
    return list(reversed(_events[-limit:]))

