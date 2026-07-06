"""In-memory upload store — acts as the temp DB for the PoC.

All uploaded CCD files, their parsed records, and processed return files are
held in module-level dicts for the lifetime of the process.

Persistence
-----------
Call ``persist()`` to snapshot the full store to ``data/store.json``.
Call ``load_from_disk()`` at application startup to restore the previous state.
A background scheduler job calls ``persist_if_dirty()`` every N seconds so data
survives restarts without manual intervention.
The ``clear()`` function resets all state (and deletes the snapshot file) for
tests and the demo-flow "Reset" button.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from payment_tracking_agent.models.payment import EntryDetailRecord, PaymentStatus, UploadRecord
from payment_tracking_agent.models.pre_submission import BatchPreSubmissionResult
from payment_tracking_agent.models.return_file import ProcessedReturnFile
from payment_tracking_agent.models.settlement import ProcessedSettlementFile

logger = logging.getLogger(__name__)

_MAX_EVENTS = 200  # cap so memory doesn't grow unbounded
_MAX_DROP_LOG = 500

# ---------------------------------------------------------------------------
# Upload store
# ---------------------------------------------------------------------------

_uploads: dict[str, UploadRecord] = {}


def save_upload(record: UploadRecord) -> None:
    """Persist an upload record keyed by its upload_id."""
    _uploads[record.upload_id] = record
    _mark_dirty()


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
        if record.uploaded_at is None:  # guard against incomplete restore from disk
            continue
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


_IN_FLIGHT_STATUSES: frozenset[PaymentStatus] = frozenset({
    # Still with bank but in the pipeline
    PaymentStatus.WITH_BANK_UPLOADED,
    PaymentStatus.WITH_BANK_VALIDATING,
    PaymentStatus.WITH_BANK_READY_FOR_SCHEME,
    # At the scheme
    PaymentStatus.WITH_SCHEME_SUBMITTED,
    PaymentStatus.WITH_SCHEME_ACKNOWLEDGED,
})


def advance_submitted_to_beneficiary_bank() -> int:
    """Advance all in-flight payments to WITH_BENEFICIARY_BANK_PENDING.

    Advances payments whose current status indicates they are anywhere in the
    submission pipeline — uploaded, validating, ready-for-scheme, submitted, or
    scheme-acknowledged.  Settlement evidence proves the batch reached the
    beneficiary bank, so all pipeline payments move forward together.

    Payments already rejected, failed validation, or already at beneficiary-bank
    stage are left untouched.

    Returns:
        Count of payments advanced.
    """
    advanced = 0
    for record in _uploads.values():
        for batch in record.parsed.batches:
            for entry in batch.entries:
                if entry.status in _IN_FLIGHT_STATUSES:
                    entry.status = PaymentStatus.WITH_BENEFICIARY_BANK_PENDING
                    entry.business_status = PaymentStatus.WITH_BENEFICIARY_BANK_PENDING.business_status
                    advanced += 1
    if advanced:
        _mark_dirty()
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
    _mark_dirty()


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
    _mark_dirty()


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

# ---------------------------------------------------------------------------
# Pre-submission validation store
# ---------------------------------------------------------------------------

_pre_submission_results: dict[str, BatchPreSubmissionResult] = {}


def save_pre_submission_result(result: BatchPreSubmissionResult) -> None:
    """Persist a pre-submission validation result keyed by upload_id."""
    _pre_submission_results[result.upload_id] = result
    _mark_dirty()


def get_pre_submission_result(upload_id: str) -> BatchPreSubmissionResult | None:
    """Return the pre-submission validation result for a given upload, or None."""
    return _pre_submission_results.get(upload_id)


def list_pre_submission_results() -> list[BatchPreSubmissionResult]:
    """Return all pre-submission results, newest first."""
    return sorted(
        _pre_submission_results.values(),
        key=lambda r: r.validated_at,
        reverse=True,
    )


def clear() -> None:
    """Remove all records (used in tests and demo reset)."""
    from payment_tracking_agent.risk.engine import invalidate_risk_cache  # noqa: PLC0415
    _uploads.clear()
    _return_files.clear()
    _settlement_files.clear()
    _pre_submission_results.clear()
    _events.clear()
    _drop_file_log.clear()
    invalidate_risk_cache()
    # Also delete the on-disk snapshot so the reset is complete
    try:
        _snapshot_path().unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
    _mark_dirty()


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


# ---------------------------------------------------------------------------
# Persistence — atomic JSON snapshot to database_json/store.json
# ---------------------------------------------------------------------------

_dirty: bool = False


def _mark_dirty() -> None:
    global _dirty
    _dirty = True


def _snapshot_path() -> Path:
    from payment_tracking_agent.config import settings  # noqa: PLC0415
    p = Path(settings.data_dir) / "store.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def persist() -> None:
    """Atomically serialize the full store to database_json/store.json.

    Writes to a .tmp file first then renames so a crash mid-write never
    leaves a corrupt snapshot.
    """
    global _dirty
    snapshot = {
        "uploads": {k: v.model_dump(mode="json") for k, v in _uploads.items()},
        "return_files": {k: v.model_dump(mode="json") for k, v in _return_files.items()},
        "settlement_files": {k: v.model_dump(mode="json") for k, v in _settlement_files.items()},
        "pre_submission_results": {
            k: v.model_dump(mode="json") for k, v in _pre_submission_results.items()
        },
        "events": _events[-_MAX_EVENTS:],
        "drop_file_log": _drop_file_log[-_MAX_DROP_LOG:],
    }
    path = _snapshot_path()
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
        _dirty = False
        logger.debug("Store persisted → %s", path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Store persist failed: %s", exc)


def persist_if_dirty() -> None:
    """Persist only when the store has unsaved changes."""
    if _dirty:
        persist()


def load_from_disk() -> None:
    """Restore store state from database_json/store.json at startup.

    Silently skips if the file does not exist or cannot be read.
    Logs a warning for individual records that fail validation so a single
    corrupt entry doesn't block the whole restore.
    """
    path = _snapshot_path()
    if not path.exists():
        logger.info("No store snapshot found at %s — starting empty.", path)
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not read store snapshot %s: %s", path, exc)
        return

    restored = {"uploads": 0, "returns": 0, "settlements": 0, "pre_sub": 0, "events": 0}

    for k, v in data.get("uploads", {}).items():
        try:
            _uploads[k] = UploadRecord.model_validate(v)
            restored["uploads"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Store load: skipping upload %s — %s", k, exc)

    for k, v in data.get("return_files", {}).items():
        try:
            _return_files[k] = ProcessedReturnFile.model_validate(v)
            restored["returns"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Store load: skipping return_file %s — %s", k, exc)

    for k, v in data.get("settlement_files", {}).items():
        try:
            _settlement_files[k] = ProcessedSettlementFile.model_validate(v)
            restored["settlements"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Store load: skipping settlement_file %s — %s", k, exc)

    for k, v in data.get("pre_submission_results", {}).items():
        try:
            _pre_submission_results[k] = BatchPreSubmissionResult.model_validate(v)
            restored["pre_sub"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Store load: skipping pre_submission %s — %s", k, exc)

    for evt in data.get("events", []):
        if isinstance(evt, dict):
            _events.append(evt)
    restored["events"] = len(data.get("events", []))

    for entry in data.get("drop_file_log", []):
        if isinstance(entry, dict):
            _drop_file_log.append(entry)

    logger.info(
        "Store restored from %s — uploads=%d returns=%d settlements=%d "
        "pre_sub=%d events=%d",
        path,
        restored["uploads"], restored["returns"], restored["settlements"],
        restored["pre_sub"], restored["events"],
    )

