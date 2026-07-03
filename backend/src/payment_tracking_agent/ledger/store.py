"""In-memory upload store — acts as the temp DB for the PoC.

All uploaded CCD files, their parsed records, and processed return files are
held in module-level dicts for the lifetime of the process.
The ``clear()`` function resets all state for tests.
"""

from __future__ import annotations

from payment_tracking_agent.models.payment import EntryDetailRecord, PaymentStatus, UploadRecord
from payment_tracking_agent.models.return_file import ProcessedReturnFile
from payment_tracking_agent.models.settlement import ProcessedSettlementFile

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


def update_all_payments_status(upload_id: str, new_status: PaymentStatus) -> None:
    """Advance every payment in an upload to *new_status*."""
    record = _uploads.get(upload_id)
    if not record:
        return
    for batch in record.parsed.batches:
        for entry in batch.entries:
            entry.status = new_status
            entry.business_status = new_status.business_status


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
# Test helpers
# ---------------------------------------------------------------------------

def clear() -> None:
    """Remove all records (used in tests)."""
    _uploads.clear()
    _return_files.clear()
    _settlement_files.clear()

