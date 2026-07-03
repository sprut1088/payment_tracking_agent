"""HTTP routes for the local-folder demo flow (Prompt 04).

Foundation endpoints only. No ACH parsing, no payment-level ledger updates —
those are added in later prompts.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Response, status

from payment_tracking_agent.models.demo_flow import (
    AcceptCorrectionRequest,
    CcdUploadOutcome,
    DemoFlowConfigView,
    DemoFlowState,
    FileKind,
    RejectCorrectionRequest,
    ScanCCDResult,
    ScanResult,
    UnderReviewItem,
)
from payment_tracking_agent.ledger import store
from payment_tracking_agent.services import return_file_service, settlement_service, upload_service
from payment_tracking_agent.services.upload_service import UploadValidationError
from payment_tracking_agent.simulator.folder_watcher import (
    FolderWatcher,
    get_folder_watcher,
)
from payment_tracking_agent.simulator.scenario_state import (
    ScenarioStateStore,
    get_scenario_state,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/demo-flow", tags=["demo-flow"])


def _archive_file(file_path: Path, processed_dir: Path, sub: str = "ccd") -> None:
    """Move *file_path* into *processed_dir/sub/* after it has been read.

    Creates the destination sub-folder if needed.  Logs but does not raise on
    failure so that a permissions error cannot break the scan endpoint.
    """
    dest_dir = processed_dir / sub
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / file_path.name
        # If a previous run left a same-named file, overwrite it.
        shutil.move(str(file_path), str(dest))
        logger.info("scan-ccd: archived %s → %s", file_path.name, dest)
    except Exception as exc:  # noqa: BLE001
        logger.warning("scan-ccd: could not archive %s: %s", file_path, exc)


@router.get("/config", response_model=DemoFlowConfigView)
def get_config(watcher: FolderWatcher = Depends(get_folder_watcher)) -> DemoFlowConfigView:
    return watcher.config_view


@router.post("/ensure-folders", response_model=DemoFlowConfigView)
def ensure_folders(
    watcher: FolderWatcher = Depends(get_folder_watcher),
) -> DemoFlowConfigView:
    watcher.ensure_directories()
    return watcher.config_view


@router.post("/scan-ccd", response_model=ScanCCDResult)
def scan_ccd(watcher: FolderWatcher = Depends(get_folder_watcher)) -> ScanCCDResult:
    """Scan the CCD inbox folder, register new batches, and parse each new file.

    For every new ``.ccd`` / ``.ach`` / ``.txt`` file discovered:
    - The batch is registered in the scenario state store (existing behaviour).
    - The file content is read and passed through the full CCD upload pipeline
      (validate → LLM-fix if needed → parse → save to payment ledger).

    Upload outcomes are included in the ``uploads`` list of the response so
    the frontend knows which files were valid and how many payments were loaded.
    """
    scan = watcher.scan_ccd()
    uploads: list[CcdUploadOutcome] = []
    cfg = watcher.config_view
    processed_dir = cfg.processed_dir
    under_review_ccd = cfg.under_review_dir / "ccd"

    for detected in scan.new_files:
        if detected.kind != FileKind.CCD:
            continue

        file_path = detected.path
        file_name = detected.filename
        batch_id = file_path.stem  # e.g. "BATCH_042" from "BATCH_042.ccd"

        # --- read bytes --------------------------------------------------
        try:
            content = file_path.read_bytes()
        except OSError as exc:
            logger.error("scan-ccd: could not read %s: %s", file_path, exc)
            uploads.append(CcdUploadOutcome(
                file_name=file_name,
                batch_id=batch_id,
                is_valid=False,
                errors=[f"Could not read file: {exc}"],
            ))
            # Archive even on read failure so the file doesn't block future scans.
            _archive_file(file_path, processed_dir)
            continue

        # --- HTTP-level preconditions ------------------------------------
        try:
            upload_service.validate_upload_preconditions(file_name, content)
        except UploadValidationError as exc:
            uploads.append(CcdUploadOutcome(
                file_name=file_name,
                batch_id=batch_id,
                is_valid=False,
                errors=[str(exc)],
            ))
            _archive_file(file_path, processed_dir)
            continue

        # --- full upload pipeline ----------------------------------------
        result = upload_service.process_ccd_upload(file_name, content)

        if result.is_valid:
            uploads.append(CcdUploadOutcome(
                file_name=file_name,
                batch_id=batch_id,
                is_valid=True,
                upload_id=result.upload_id,
                entry_count=result.entry_count,
                batch_count=result.batch_count,
            ))
            # Valid — archive to processed/ccd/
            _archive_file(file_path, processed_dir)
        else:
            # Invalid — move to under-review/ccd/ and save corrections alongside.
            errors_list = [
                f"Line {e.line_number} [{e.field}]: {e.issue}"
                for e in result.validation_errors
            ]
            corrected_lines_data = [
                {"line_number": cl.line_number, "line": cl.line, "was_corrected": cl.was_corrected, "explanation": cl.explanation}
                for cl in result.corrected_lines
            ] if result.corrected_lines else None

            try:
                under_review_ccd.mkdir(parents=True, exist_ok=True)
                dest_orig = under_review_ccd / file_path.name
                shutil.move(str(file_path), str(dest_orig))
                corrections_path = under_review_ccd / (file_path.stem + ".corrections.json")
                corrections_path.write_text(json.dumps({
                    "errors": errors_list,
                    "corrected_file_content": result.corrected_file_content,
                    "corrected_lines": corrected_lines_data,
                }, indent=2, ensure_ascii=False))
                logger.info("scan-ccd: moved %s to under-review", file_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("scan-ccd: could not move %s to under-review: %s", file_path, exc)

            uploads.append(CcdUploadOutcome(
                file_name=file_name,
                batch_id=batch_id,
                is_valid=False,
                errors=errors_list,
                validation_error_count=len(result.validation_errors),
                corrected_file_content=result.corrected_file_content,
                corrected_lines=corrected_lines_data,
                is_awaiting_review=True,
            ))

    return ScanCCDResult(
        scanned_at=scan.scanned_at,
        new_files=scan.new_files,
        new_batches=scan.new_batches,
        batches_advanced=scan.batches_advanced,
        uploads=uploads,
    )


@router.post("/accept-correction", response_model=CcdUploadOutcome)
def accept_correction(
    body: AcceptCorrectionRequest,
    watcher: FolderWatcher = Depends(get_folder_watcher),
) -> CcdUploadOutcome:
    """Accept corrections for an invalid CCD file, process it, and clean up under-review."""
    content_bytes = body.corrected_content.encode("ascii", errors="replace")

    try:
        upload_service.validate_upload_preconditions(body.file_name, content_bytes)
    except UploadValidationError as exc:
        return CcdUploadOutcome(
            file_name=body.file_name,
            batch_id=body.batch_id,
            is_valid=False,
            errors=[str(exc)],
        )

    result = upload_service.process_ccd_upload(body.file_name, content_bytes)

    if result.is_valid:
        # Clean up the under-review files for this batch.
        under_review_ccd = watcher.config_view.under_review_dir / "ccd"
        processed_ccd = watcher.config_view.processed_dir / "ccd"
        if under_review_ccd.exists():
            processed_ccd.mkdir(parents=True, exist_ok=True)
            for f in under_review_ccd.glob(f"{body.batch_id}.*"):
                try:
                    shutil.move(str(f), str(processed_ccd / f.name))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("accept-correction: could not move %s: %s", f, exc)

        return CcdUploadOutcome(
            file_name=body.file_name,
            batch_id=body.batch_id,
            is_valid=True,
            upload_id=result.upload_id,
            entry_count=result.entry_count,
            batch_count=result.batch_count,
        )

    # Still invalid after correction — return errors + fresh corrections.
    return CcdUploadOutcome(
        file_name=body.file_name,
        batch_id=body.batch_id,
        is_valid=False,
        errors=[
            f"Line {e.line_number} [{e.field}]: {e.issue}"
            for e in result.validation_errors
        ],
        validation_error_count=len(result.validation_errors),
        corrected_file_content=result.corrected_file_content,
        corrected_lines=[
            {"line_number": cl.line_number, "line": cl.line, "was_corrected": cl.was_corrected, "explanation": cl.explanation}
            for cl in result.corrected_lines
        ] if result.corrected_lines else None,
        is_awaiting_review=True,
    )


@router.get("/under-review", response_model=list[UnderReviewItem])
def get_under_review(
    watcher: FolderWatcher = Depends(get_folder_watcher),
) -> list[UnderReviewItem]:
    """Return all CCD files currently in the under-review queue."""
    under_review_ccd = watcher.config_view.under_review_dir / "ccd"
    if not under_review_ccd.exists():
        return []

    items: list[UnderReviewItem] = []
    for corrections_file in sorted(under_review_ccd.glob("*.corrections.json")):
        stem = corrections_file.stem.replace(".corrections", "")
        # Find the original file (anything that isn't the corrections JSON).
        orig_candidates = [
            f for f in under_review_ccd.glob(f"{stem}.*")
            if not f.name.endswith(".corrections.json")
        ]
        if not orig_candidates:
            continue
        orig_file = orig_candidates[0]
        try:
            original_content = orig_file.read_text(encoding="ascii", errors="replace")
            corrections_data: dict = json.loads(corrections_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("under-review: could not read %s: %s", orig_file, exc)
            continue
        items.append(UnderReviewItem(
            file_name=orig_file.name,
            batch_id=stem,
            discovered_at=datetime.fromtimestamp(
                orig_file.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
            errors=corrections_data.get("errors", []),
            original_content=original_content,
            corrected_file_content=corrections_data.get("corrected_file_content"),
            corrected_lines=corrections_data.get("corrected_lines"),
        ))
    return items


@router.post("/reject-correction", status_code=status.HTTP_204_NO_CONTENT)
def reject_correction(
    body: RejectCorrectionRequest,
    watcher: FolderWatcher = Depends(get_folder_watcher),
) -> Response:
    """Reject all corrections for a file — move it from under-review to processed/rejected."""
    under_review_ccd = watcher.config_view.under_review_dir / "ccd"
    rejected_dir = watcher.config_view.processed_dir / "ccd" / "rejected"
    rejected_dir.mkdir(parents=True, exist_ok=True)

    if under_review_ccd.exists():
        for f in under_review_ccd.glob(f"{body.batch_id}.*"):
            try:
                shutil.move(str(f), str(rejected_dir / f.name))
            except Exception as exc:  # noqa: BLE001
                logger.warning("reject-correction: could not move %s: %s", f, exc)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/check-settlement", response_model=ScanResult)
def check_settlement(watcher: FolderWatcher = Depends(get_folder_watcher)) -> ScanResult:
    """Scan for new settlement and scheme-reject files and update the payment ledger.

    - Settlement summary files → advance all WITH_SCHEME_SUBMITTED payments to
      WITH_BENEFICIARY_BANK (summary-level evidence; no payment-level clearing claimed).
    - Scheme-reject files → parse trace numbers and mark matched payments
      REJECTED_BY_SCHEME via settlement_service.
    """
    scan = watcher.check_settlement()

    # Process newly detected files and update the payment ledger.
    for detected in scan.new_files:
        try:
            content = detected.path.read_bytes()
        except OSError as exc:
            logger.warning("check-settlement: could not read %s: %s", detected.path, exc)
            continue

        if detected.kind == FileKind.SCHEME_REJECT:
            # Parse the reject file and mark specific payments REJECTED_BY_SCHEME.
            try:
                result = settlement_service.process_settlement_file(
                    detected.filename, content
                )
                logger.info(
                    "check-settlement: scheme-reject %s — matched=%d unmatched=%d",
                    detected.filename,
                    result.matched_count,
                    result.unmatched_count,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "check-settlement: failed to process scheme-reject %s: %s",
                    detected.filename, exc, exc_info=True,
                )

        elif detected.kind == FileKind.SETTLEMENT:
            # Settlement summary — advance all submitted payments to WITH_BENEFICIARY_BANK.
            # Per SME rules: summary evidence only; no payment-level clearing is claimed.
            advanced = store.advance_submitted_to_beneficiary_bank()
            store.append_event(
                "PaymentLifecycleOrchestrator",
                f"Settlement summary received — {detected.filename}: {advanced} payment(s) "
                "advanced to WITH BENEFICIARY BANK. "
                "Summary-level evidence only; no payment-level clearing is claimed.",
            )
            logger.info(
                "check-settlement: settlement summary %s — advanced %d payment(s) "
                "to WITH_BENEFICIARY_BANK",
                detected.filename,
                advanced,
            )

    return scan


@router.post("/check-returns", response_model=ScanResult)
def check_returns(watcher: FolderWatcher = Depends(get_folder_watcher)) -> ScanResult:
    """Scan for new NACHA return files and update the payment ledger.

    Each return file is parsed and matched back to stored payments by original
    trace number.  Matched payments are advanced to REJECTED_BY_BENEFICIARY_BANK.
    """
    scan = watcher.check_returns()

    for detected in scan.new_files:
        if detected.kind != FileKind.RETURN:
            continue
        try:
            content = detected.path.read_bytes()
        except OSError as exc:
            logger.warning("check-returns: could not read %s: %s", detected.path, exc)
            continue
        try:
            result = return_file_service.process_return_file(detected.filename, content)
            logger.info(
                "check-returns: return file %s — matched=%d unmatched=%d",
                detected.filename,
                result.matched_count,
                result.unmatched_count,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "check-returns: failed to process return file %s: %s",
                detected.filename, exc, exc_info=True,
            )

    return scan


@router.get("/state", response_model=DemoFlowState)
def get_state(store: ScenarioStateStore = Depends(get_scenario_state)) -> DemoFlowState:
    return DemoFlowState(
        as_of=datetime.now(timezone.utc),
        batches=store.list_batches(),
        detected_files=store.list_detected_files(),
    )


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset(store: ScenarioStateStore = Depends(get_scenario_state)) -> None:
    store.reset()
