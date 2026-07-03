"""HTTP routes for ACH payment tracking.

Each handler is intentionally thin:
  - read HTTP input
  - call the service layer
  - map the result to an HTTP response

All business logic lives in ``payment_tracking_agent.services``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from payment_tracking_agent import __version__
from payment_tracking_agent.ledger import store
from payment_tracking_agent.models.payment import PaymentStatus
from payment_tracking_agent.models.transaction_status import (
    CustomerSummaryItem,
    FileTransactionsResponse,
    PaymentListItem,
    TransactionStatus,
)
from payment_tracking_agent.risk.engine import compute_customer_risk
from payment_tracking_agent.services import return_file_service, settlement_service, upload_service
from payment_tracking_agent.services.upload_service import UploadValidationError

router = APIRouter()


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/api/v1/events", tags=["Events"])
def list_events(limit: int = 100) -> list[dict]:
    """Return recent system events from the payment ledger, newest first.

    Each event has: ``timestamp``, ``cycleTime``, ``agent``, ``message``.
    """
    return store.list_events(limit=min(limit, 200))


# ---------------------------------------------------------------------------
# CCD upload
# ---------------------------------------------------------------------------

@router.post("/api/v1/upload/ccd", tags=["CCD Upload"])
async def upload_ccd_file(file: UploadFile) -> JSONResponse:
    """Upload, validate, and (if valid) persist an ACH CCD file.

    Delegates entirely to ``upload_service.process_ccd_upload``.
    Returns HTTP 201 when the file is valid and saved, or
    HTTP 422 when syntax errors are found (includes LLM fix suggestions).
    """
    file_name = file.filename or "unknown"
    content = await file.read()

    try:
        upload_service.validate_upload_preconditions(file_name, content)
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    result = upload_service.process_ccd_upload(file_name, content)

    status_code = 201 if result.is_valid else 422
    return JSONResponse(status_code=status_code, content=result.model_dump(mode="json"))


@router.post("/api/v1/upload/ccd/download-corrected", tags=["CCD Upload"])
async def download_corrected_file(
    content: str = Body(..., media_type="text/plain"),
    filename: str = "corrected.ach",
) -> PlainTextResponse:
    """Return the corrected file content as a downloadable plain-text file.

    Paste the value of ``corrected_file_content`` from the upload response
    as the request body.  The response can be saved directly as a ``.ach`` file.
    """
    if not content.strip():
        raise HTTPException(status_code=400, detail="Content must not be empty.")
    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Query endpoints
# ---------------------------------------------------------------------------

@router.get("/api/v1/uploads", tags=["CCD Upload"])
def list_uploads() -> list[dict]:
    """Return a summary list of all uploaded CCD files (newest first)."""
    return [
        {
            "upload_id": r.upload_id,
            "file_name": r.file_name,
            "uploaded_at": r.uploaded_at.isoformat(),
            "entry_count": r.entry_count,
            "batch_count": r.batch_count,
        }
        for r in store.list_uploads()
    ]


@router.get("/api/v1/uploads/{upload_id}", tags=["CCD Upload"])
def get_upload(upload_id: str) -> dict:
    """Return full detail for a single upload, including all parsed payment records."""
    record = store.get_upload(upload_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    return record.model_dump(mode="json")


@router.get(
    "/api/v1/uploads/{upload_id}/transactions",
    response_model=FileTransactionsResponse,
    tags=["Transactions"],
)
def get_file_transactions(upload_id: str) -> FileTransactionsResponse:
    """Return file metadata and every transaction's current lifecycle status.

    Summary counts are grouped by business status
    (WITH BANK / WITH SCHEME / WITH BENEFICIARY BANK / CLEARED / REJECTED).
    """
    record = store.get_upload(upload_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Upload not found.")

    fh = record.parsed.file_header
    transactions: list[TransactionStatus] = []
    summary: dict[str, int] = {}

    for batch in record.parsed.batches:
        for entry in batch.entries:
            bs = entry.business_status
            summary[bs] = summary.get(bs, 0) + 1
            transactions.append(
                TransactionStatus(
                    trace_number=entry.trace_number,
                    batch_number=entry.batch_number,
                    sec_code=entry.sec_code,
                    transaction_code=entry.transaction_code,
                    receiving_dfi=entry.receiving_dfi,
                    check_digit=entry.check_digit,
                    dfi_account_number_masked=entry.dfi_account_number_masked,
                    individual_id_number=entry.individual_id_number,
                    individual_name=entry.individual_name,
                    amount=entry.amount,
                    amount_cents=entry.amount_cents,
                    addenda_indicator=entry.addenda_indicator,
                    status=entry.status.value,
                    business_status=bs,
                    corrective_action=entry.corrective_action,
                )
            )

    return FileTransactionsResponse(
        upload_id=record.upload_id,
        file_name=record.file_name,
        uploaded_at=record.uploaded_at,
        entry_count=record.entry_count,
        batch_count=record.batch_count,
        immediate_destination=fh.immediate_destination,
        immediate_origin=fh.immediate_origin,
        file_creation_date=fh.file_creation_date,
        file_creation_time=fh.file_creation_time,
        immediate_destination_name=fh.immediate_destination_name,
        immediate_origin_name=fh.immediate_origin_name,
        summary=summary,
        transactions=transactions,
    )


# ---------------------------------------------------------------------------
# Cross-file payment queries
# ---------------------------------------------------------------------------

@router.get(
    "/api/v1/payments",
    response_model=list[PaymentListItem],
    tags=["Transactions"],
)
def list_payments(
    status: str | None = None,
    business_status: str | None = None,
    upload_id: str | None = None,
) -> list[PaymentListItem]:
    """List every tracked payment across all uploaded files.

    Optional query params:
    - ``status``          — filter by internal sub-status (e.g. ``WITH_BANK_UPLOADED``)
    - ``business_status`` — filter by business status (e.g. ``WITH BANK``)
    - ``upload_id``       — filter to a single file
    """
    results: list[PaymentListItem] = []
    uploads = [store.get_upload(upload_id)] if upload_id else store.list_uploads()

    # Fetch timestamped history once; the risk engine filters per customer internally.
    # Cache risk per customer so the LLM (if enabled) is called once per customer,
    # not once per payment row.
    history = store.list_all_entries_with_timestamps()
    risk_cache: dict[str, tuple[str, str | None]] = {}

    def _get_risk(cid: str) -> tuple[str, str | None]:
        if cid not in risk_cache:
            lvl, reason = compute_customer_risk(cid, history)
            risk_cache[cid] = (lvl, reason)
        return risk_cache[cid]

    for record in uploads:
        if record is None:
            continue
        for batch in record.parsed.batches:
            for entry in batch.entries:
                if status and entry.status.value != status:
                    continue
                if business_status and entry.business_status != business_status:
                    continue
                risk_level, risk_reason = _get_risk(
                    entry.individual_id_number or entry.trace_number
                )
                results.append(
                    PaymentListItem(
                        upload_id=record.upload_id,
                        file_name=record.file_name,
                        uploaded_at=record.uploaded_at,
                        trace_number=entry.trace_number,
                        batch_number=entry.batch_number,
                        individual_name=entry.individual_name,
                        individual_id_number=entry.individual_id_number,
                        amount=entry.amount,
                        amount_cents=entry.amount_cents,
                        receiving_dfi=entry.receiving_dfi,
                        dfi_account_number_masked=entry.dfi_account_number_masked,
                        status=entry.status.value,
                        business_status=entry.business_status,
                        corrective_action=entry.corrective_action,
                        return_reason_code=entry.return_reason_code,
                        return_reason_description=entry.return_reason_description,
                        return_customer_message=entry.return_customer_message,
                        risk_level=risk_level,
                        risk_reason=risk_reason,
                    )
                )
    return results


@router.get(
    "/api/v1/customers",
    response_model=list[CustomerSummaryItem],
    tags=["Transactions"],
)
def list_customers() -> list[CustomerSummaryItem]:
    """Return one aggregated row per unique customer (individual_id_number).

    Counts are grouped from the full payment ledger.  Risk level is computed
    once per customer using the time-aware risk engine.
    """
    # Build per-customer payment buckets
    by_customer: dict[str, list] = {}
    for record in store.list_uploads():
        for batch in record.parsed.batches:
            for entry in batch.entries:
                cid = entry.individual_id_number or entry.trace_number
                by_customer.setdefault(cid, []).append(entry)

    if not by_customer:
        return []

    history = store.list_all_entries_with_timestamps()
    risk_cache: dict[str, tuple[str, str | None]] = {}

    def _get_risk(cid: str) -> tuple[str, str | None]:
        if cid not in risk_cache:
            risk_cache[cid] = compute_customer_risk(cid, history)
        return risk_cache[cid]

    _SCHEME_STATUSES = (
        PaymentStatus.WITH_SCHEME_SUBMITTED,
        PaymentStatus.WITH_SCHEME_ACKNOWLEDGED,
    )
    _BENEFICIARY_STATUSES = (PaymentStatus.WITH_BENEFICIARY_BANK_PENDING,)
    _REJECTED_SCHEME = (PaymentStatus.REJECTED_BY_SETTLEMENT,)
    _REJECTED_RETURN = (PaymentStatus.REJECTED_BY_RETURN_FILE,)

    results: list[CustomerSummaryItem] = []
    for cid, entries in by_customer.items():
        risk_level, risk_reason = _get_risk(cid)
        results.append(
            CustomerSummaryItem(
                customer_id=cid,
                customer_name=entries[0].individual_name or "Unknown",
                total_payments=len(entries),
                sent_to_scheme=sum(1 for e in entries if e.status in _SCHEME_STATUSES),
                with_beneficiary_bank=sum(1 for e in entries if e.status in _BENEFICIARY_STATUSES),
                rejected_by_scheme=sum(1 for e in entries if e.status in _REJECTED_SCHEME),
                rejected_by_beneficiary_bank=sum(1 for e in entries if e.status in _REJECTED_RETURN),
                last_rejection_date=None,  # no per-entry timestamp available
                historical_rejection_count=sum(
                    1 for e in entries
                    if e.status in (*_REJECTED_SCHEME, *_REJECTED_RETURN)
                ),
                risk_level=risk_level,
                risk_reason=risk_reason,
            )
        )
    # Sort: highest risk first, then most rejections
    _risk_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    results.sort(key=lambda r: (_risk_order.get(r.risk_level, 9), -r.historical_rejection_count))
    return results


@router.get(
    "/api/v1/payments/{trace_number}",
    response_model=TransactionStatus,
    tags=["Transactions"],
)
def get_payment(trace_number: str) -> TransactionStatus:
    """Look up a single payment by its NACHA trace number.

    Returns the current lifecycle status together with all field values.
    """
    record, entry = store.find_payment_by_trace(trace_number)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Payment with trace '{trace_number}' not found.")
    return TransactionStatus(
        trace_number=entry.trace_number,
        batch_number=entry.batch_number,
        sec_code=entry.sec_code,
        transaction_code=entry.transaction_code,
        receiving_dfi=entry.receiving_dfi,
        check_digit=entry.check_digit,
        dfi_account_number_masked=entry.dfi_account_number_masked,
        individual_id_number=entry.individual_id_number,
        individual_name=entry.individual_name,
        amount=entry.amount,
        amount_cents=entry.amount_cents,
        addenda_indicator=entry.addenda_indicator,
        status=entry.status.value,
        business_status=entry.business_status,
        corrective_action=entry.corrective_action,
        return_reason_code=entry.return_reason_code,
        return_reason_description=entry.return_reason_description,
        return_customer_message=entry.return_customer_message,
    )


# ---------------------------------------------------------------------------
# NACHA return file upload
# ---------------------------------------------------------------------------

_RETURN_ALLOWED_EXTENSIONS = {".ach", ".txt", ".dat", ""}
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/api/v1/upload/return", status_code=201, tags=["Return Files"])
async def upload_return_file(file: UploadFile) -> JSONResponse:
    """Upload a NACHA return file.

    - Parses every returned entry detail record (type 6 / type 7).
    - Matches each trace number back to a stored payment.
    - Advances matched payments to ``WITH_BENEFICIARY_BANK_PENDING``
      (business status: **WITH BENEFICIARY BANK**).
    - Saves the raw file to ``settings.return_dir``.

    Returns the full ``ProcessedReturnFile`` with per-record match results.
    """
    file_name = file.filename or "unknown"
    suffix = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if f".{suffix}" not in _RETURN_ALLOWED_EXTENSIONS and suffix not in _RETURN_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension. Allowed: {sorted(_RETURN_ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded return file is empty.")
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds maximum allowed size of 10 MB.")

    result = return_file_service.process_return_file(file_name, content)
    return JSONResponse(status_code=201, content=result.model_dump(mode="json"))


@router.get("/api/v1/returns", tags=["Return Files"])
def list_return_files() -> list[dict]:
    """Return a summary list of all processed NACHA return files."""
    return [
        {
            "return_file_id": r.return_file_id,
            "file_name": r.file_name,
            "processed_at": r.processed_at.isoformat(),
            "matched_count": r.matched_count,
            "unmatched_count": r.unmatched_count,
        }
        for r in store.list_return_files()
    ]


@router.get("/api/v1/returns/{return_file_id}", tags=["Return Files"])
def get_return_file(return_file_id: str) -> dict:
    """Return full detail for a processed return file, including per-record match results."""
    record = store.get_return_file(return_file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Return file not found.")
    return record.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Settlement rejection file upload
# ---------------------------------------------------------------------------

_SETTLEMENT_ALLOWED_EXTENSIONS = {".csv", ".txt", ".dat", ""}


@router.post("/api/v1/upload/settlement", status_code=201, tags=["Settlement Files"])
async def upload_settlement_file(file: UploadFile) -> JSONResponse:
    """Upload a settlement rejection file.

    - Parses each rejected payment record (trace number + reason code + reason text).
    - Calls the LLM **once** (batched by unique reason code) to generate
      corrective action guidance for operations staff.
    - Matches each trace number to a stored payment and advances its status to
      ``REJECTED_BY_SETTLEMENT`` (business status: **REJECTED**).
    - Attaches the LLM corrective action to each matched payment record.
    - Saves the raw file to ``settings.settlement_dir``.

    Returns the full ``ProcessedSettlementFile`` with per-record results and
    LLM suggestions.
    """
    file_name = file.filename or "unknown"
    suffix = Path(file_name).suffix.lower()
    if suffix not in _SETTLEMENT_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension. Allowed: {sorted(_SETTLEMENT_ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded settlement file is empty.")
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds maximum allowed size of 10 MB.")

    result = settlement_service.process_settlement_file(file_name, content)
    return JSONResponse(status_code=201, content=result.model_dump(mode="json"))


@router.get("/api/v1/settlements", tags=["Settlement Files"])
def list_settlement_files() -> list[dict]:
    """Return a summary list of all processed settlement files."""
    return [
        {
            "settlement_file_id": r.settlement_file_id,
            "file_name": r.file_name,
            "processed_at": r.processed_at.isoformat(),
            "matched_count": r.matched_count,
            "unmatched_count": r.unmatched_count,
            "reason_codes_seen": r.reason_codes_seen,
        }
        for r in store.list_settlement_files()
    ]


@router.get("/api/v1/settlements/{settlement_file_id}", tags=["Settlement Files"])
def get_settlement_file(settlement_file_id: str) -> dict:
    """Return full detail for a settlement file, including LLM corrective actions per record."""
    record = store.get_settlement_file(settlement_file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Settlement file not found.")
    return record.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Drop folder status
# ---------------------------------------------------------------------------

class DropFileInfo(BaseModel):
    filename: str
    subfolder: str   # e.g. "ccd/input", "settlement/processed"
    size_bytes: int
    modified_at: str  # ISO-8601


class DropStatusResponse(BaseModel):
    files: list[DropFileInfo]
    scanned_at: str  # ISO-8601


@router.get("/api/v1/drop-status", tags=["Drop Folders"])
def get_drop_status() -> DropStatusResponse:
    """Return files processed by the scheduler from any drop/ input folder.

    Data comes from the in-memory processing log recorded by the scheduler jobs
    at the time each file is moved to processed/, error/, or under-review/.
    No filesystem scan is performed.
    """
    from datetime import datetime, timezone

    files = [
        DropFileInfo(
            filename=entry["filename"],
            subfolder=f"{entry['file_type']}/{entry['outcome']}",
            size_bytes=entry["size_bytes"],
            modified_at=entry["processed_at"],
        )
        for entry in store.list_drop_files()
    ]

    return DropStatusResponse(
        files=files,
        scanned_at=datetime.now(tz=timezone.utc).isoformat(),
    )
