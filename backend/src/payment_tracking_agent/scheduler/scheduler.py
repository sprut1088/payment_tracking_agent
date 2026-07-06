"""APScheduler background jobs for automated ACH processing.

Four recurring file-scanning jobs plus two lifecycle-advance jobs:

1. ``ccd_scanner``
   Polls ``settings.ccd_scan_dir`` (drop/ccd/input/) for new .ach / .txt / .dat
   files and passes each to ``upload_service.process_ccd_upload``.
   - Valid files  → drop/ccd/processed/
   - Syntax errors → drop/ccd/under-review/
   - Unprocessable → drop/ccd/error/

2. ``return_file_scanner``
   Polls ``settings.return_scan_dir`` (drop/returns/input/) for new .ach / .txt
   files and passes each to ``return_file_service.process_return_file``.
   - Processed → drop/returns/processed/
   - Error      → drop/returns/error/

3. ``scheme_pusher``
   Calls ``scheme_service.push_pending_uploads_to_scheme`` to advance
   WITH_BANK_UPLOADED payments to WITH_SCHEME_SUBMITTED.

4. ``settlement_scanner``
   Polls ``settings.settlement_scan_dir`` (drop/settlement/input/) for new
   .csv / .txt / .dat files and passes each to
   ``settlement_service.process_settlement_file``.
   - Processed → drop/settlement/processed/
   - Error      → drop/settlement/error/

5. ``settlement_simulator``
   Auto-advances WITH_SCHEME_SUBMITTED payments to WITH_BENEFICIARY_BANK after
   the configured interval (summary-level evidence only — no clearing claimed).

Frontend buttons use demo-inbox/ folders; the scheduler watches drop/ folders.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from payment_tracking_agent.config import settings

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler(timezone="UTC")


def _move_unique(src: Path, dest_dir: Path) -> Path:
    """Move *src* into *dest_dir*, appending a timestamp suffix if a file with
    the same name already exists in the destination directory.

    Returns the final destination path.
    """
    dest = dest_dir / src.name
    if dest.exists():
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
        stem = src.stem
        suffix = src.suffix
        dest = dest_dir / f"{stem}_{ts}{suffix}"
    shutil.move(str(src), str(dest))
    return dest


# ---------------------------------------------------------------------------
# Job implementations  (lazy imports to avoid circular dependencies)
# ---------------------------------------------------------------------------

def _job_scan_return_files() -> None:
    """Scan drop/returns/input/ and process any new return files.

    Processed files are moved to drop/returns/processed/.
    Unprocessable files are moved to drop/returns/error/.
    """
    from payment_tracking_agent.ledger import store
    from payment_tracking_agent.services import return_file_service

    scan_dir = Path(settings.return_scan_dir)
    if not scan_dir.exists():
        return

    processed_dir = Path(settings.return_scan_processed_dir)
    error_dir = Path(settings.return_scan_error_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    error_dir.mkdir(parents=True, exist_ok=True)

    for path in sorted(scan_dir.glob("*.ach")) + sorted(scan_dir.glob("*.txt")):
        logger.info("Scheduler [return_file_scanner]: processing %s", path.name)
        try:
            content = path.read_bytes()
            result = return_file_service.process_return_file(path.name, content)
            logger.info(
                "Scheduler [return_file_scanner]: %s — matched=%d unmatched=%d",
                path.name,
                result.matched_count,
                result.unmatched_count,
            )
            _move_unique(path, processed_dir)
            store.record_drop_file(
                filename=path.name,
                file_type="returns",
                outcome="processed",
                size_bytes=len(content),
                detail=f"matched={result.matched_count} unmatched={result.unmatched_count}",
            )
            if result.matched_count > 0:
                from payment_tracking_agent.risk.engine import invalidate_risk_cache  # noqa: PLC0415
                invalidate_risk_cache()
        except Exception as exc:
            logger.error(
                "Scheduler [return_file_scanner]: failed to process %s — %s",
                path,
                exc,
            )
            _move_unique(path, error_dir)
            store.record_drop_file(
                filename=path.name,
                file_type="returns",
                outcome="error",
                size_bytes=path.stat().st_size if path.exists() else 0,
                detail=str(exc),
            )
            store.append_event(
                "ReturnFileAgent",
                f"Return file error — {path.name}: could not be parsed. {exc}",
            )


def _job_push_to_scheme() -> None:
    """Push pending uploads to the scheme folder."""
    from payment_tracking_agent.services import scheme_service

    pushed = scheme_service.push_pending_uploads_to_scheme()
    if pushed:
        logger.info(
            "Scheduler [scheme_pusher]: pushed %d upload(s) — %s",
            len(pushed),
            pushed,
        )


def _job_simulate_settlement() -> None:
    """Auto-advance all SENT_TO_SCHEME payments to WITH_BENEFICIARY_BANK.

    Simulates the FedACH settlement summary arriving automatically after the
    configured interval.  No payment-level clearing is claimed — this mirrors
    the summary-level evidence rule from the SME-confirmed lifecycle.
    """
    from payment_tracking_agent.ledger import store

    advanced = store.advance_submitted_to_beneficiary_bank()
    if advanced:
        store.append_event(
            "PaymentLifecycleOrchestrator",
            f"Settlement simulation — {advanced} payment(s) advanced from "
            "SENT TO SCHEME to WITH BENEFICIARY BANK. "
            "Settlement is summary-level evidence only; no payment-level clearing is claimed.",
        )
        logger.info(
            "Scheduler [settlement_simulator]: advanced %d payment(s) "
            "SENT_TO_SCHEME → WITH_BENEFICIARY_BANK (summary-level evidence only)",
            advanced,
        )


def _job_scan_settlement_files() -> None:
    """Scan drop/settlement/input/ and process any new scheme-reject / settlement files.

    Each file is handled in two passes (matching what demo_flow check-settlement does):
    1. Trace-level scheme-reject matching via settlement_service.
    2. Bulk advance of all WITH_SCHEME_SUBMITTED payments to WITH_BENEFICIARY_BANK
       (SME rule: any settlement file = summary evidence that batch reached beneficiary bank).

    Processed files are moved to drop/settlement/processed/.
    Unprocessable files are moved to drop/settlement/error/.
    """
    from payment_tracking_agent.ledger import store
    from payment_tracking_agent.services import settlement_service

    scan_dir = Path(settings.settlement_scan_dir)
    if not scan_dir.exists():
        return

    processed_dir = Path(settings.settlement_scan_processed_dir)
    error_dir = Path(settings.settlement_scan_error_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    error_dir.mkdir(parents=True, exist_ok=True)

    all_files = (
        sorted(scan_dir.glob("*.csv"))
        + sorted(scan_dir.glob("*.txt"))
        + sorted(scan_dir.glob("*.dat"))
    )
    for path in all_files:
        logger.info("Scheduler [settlement_scanner]: processing %s", path.name)
        try:
            content = path.read_bytes()

            # Pass 1 — scheme-reject trace matching
            result = settlement_service.process_settlement_file(path.name, content)
            logger.info(
                "Scheduler [settlement_scanner]: %s — scheme-reject matched=%d unmatched=%d",
                path.name,
                result.matched_count,
                result.unmatched_count,
            )

            # Pass 2 — bulk advance any SENT TO SCHEME → WITH BENEFICIARY BANK
            advanced = store.advance_submitted_to_beneficiary_bank()
            if advanced > 0:
                store.append_event(
                    "SchemeAndSettlementAgent",
                    f"Settlement file received — {path.name}: {advanced} payment(s) advanced "
                    "to WITH BENEFICIARY BANK. "
                    "Summary-level evidence only; no payment-level clearing is claimed.",
                )
                logger.info(
                    "Scheduler [settlement_scanner]: %s — advanced %d payment(s) "
                    "SENT_TO_SCHEME → WITH_BENEFICIARY_BANK",
                    path.name,
                    advanced,
                )
            else:
                store.append_event(
                    "SchemeAndSettlementAgent",
                    f"Settlement file received — {path.name}: file processed successfully. "
                    "No payments currently at SENT TO SCHEME stage to advance.",
                )

            _move_unique(path, processed_dir)
            store.record_drop_file(
                filename=path.name,
                file_type="settlement",
                outcome="processed",
                size_bytes=len(content),
                detail=f"scheme-reject matched={result.matched_count} advanced={advanced}",
            )
            if result.matched_count > 0 or advanced > 0:
                from payment_tracking_agent.risk.engine import invalidate_risk_cache  # noqa: PLC0415
                invalidate_risk_cache()
        except Exception as exc:
            logger.error(
                "Scheduler [settlement_scanner]: failed to process %s — %s", path, exc
            )
            _move_unique(path, error_dir)
            store.record_drop_file(
                filename=path.name,
                file_type="settlement",
                outcome="error",
                size_bytes=path.stat().st_size if path.exists() else 0,
                detail=str(exc),
            )
            store.append_event(
                "SchemeAndSettlementAgent",
                f"Settlement file error — {path.name}: could not be parsed. {exc}",
            )


def _job_scan_ccd_files() -> None:
    """Scan drop/ccd/input/ and process any new CCD files.

    File lifecycle:
    - Parsed OK → drop/ccd/processed/
    - Parsed but has syntax errors (under review) → drop/ccd/under-review/
    - Completely unprocessable → drop/ccd/error/
    """
    from payment_tracking_agent.ledger import store
    from payment_tracking_agent.services import upload_service

    scan_dir = Path(settings.ccd_scan_dir)
    if not scan_dir.exists():
        return

    processed_dir = Path(settings.ccd_scan_processed_dir)
    under_review_dir = Path(settings.ccd_scan_under_review_dir)
    error_dir = Path(settings.ccd_scan_error_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    under_review_dir.mkdir(parents=True, exist_ok=True)
    error_dir.mkdir(parents=True, exist_ok=True)

    all_files = (
        sorted(scan_dir.glob("*.ach"))
        + sorted(scan_dir.glob("*.txt"))
        + sorted(scan_dir.glob("*.dat"))
    )
    for path in all_files:
        logger.info("Scheduler [ccd_scanner]: processing %s", path.name)
        try:
            content = path.read_bytes()
            upload_service.validate_upload_preconditions(path.name, content)
            result = upload_service.process_ccd_upload(path.name, content)
            if result.is_valid:
                logger.info(
                    "Scheduler [ccd_scanner]: %s — valid, %d payment(s) created",
                    path.name,
                    result.entry_count,
                )
                _move_unique(path, processed_dir)
                store.record_drop_file(
                    filename=path.name,
                    file_type="ccd",
                    outcome="processed",
                    size_bytes=len(content),
                    detail=f"{result.entry_count} payment(s) created",
                )
                store.append_event(
                    "BeforePaymentSubmissionAgent",
                    f"CCD file received — {path.name}: {result.entry_count} payment(s) created "
                    "and moved to SENT TO SCHEME after bank-side validation passed.",
                )
                # Run pre-submission risk validation immediately so risk is
                # visible on the Batch Dashboard before the scheme_pusher fires.
                try:
                    from payment_tracking_agent.services import pre_submission_service  # noqa: PLC0415
                    upload_rec = store.get_upload(result.upload_id) if result.upload_id else None
                    if upload_rec:
                        validation = pre_submission_service.validate_batch_before_submission(upload_rec)
                        store.save_pre_submission_result(validation)
                        store.append_event(
                            "BeforePaymentSubmissionAgent",
                            f"Pre-submission risk — {path.name}: "
                            f"{validation.ai_batch_summary} "
                            f"(batch risk={validation.batch_risk_level} "
                            f"hold={validation.hold_count} review={validation.review_count} "
                            f"proceed={validation.proceed_count})",
                        )
                        logger.info(
                            "Scheduler [ccd_scanner]: pre-submission risk — %s risk=%s hold=%d review=%d proceed=%d",
                            path.name, validation.batch_risk_level,
                            validation.hold_count, validation.review_count, validation.proceed_count,
                        )
                except Exception as _ps_exc:  # noqa: BLE001
                    logger.warning(
                        "Scheduler [ccd_scanner]: pre-submission validation failed for %s: %s",
                        path.name, _ps_exc, exc_info=True,
                    )
            else:
                logger.warning(
                    "Scheduler [ccd_scanner]: %s — syntax errors, moved to under-review",
                    path.name,
                )
                _move_unique(path, under_review_dir)
                # Write corrections JSON so the review panel can display errors
                corrections_path = under_review_dir / (path.stem + ".corrections.json")
                try:
                    corrections_data = {
                        "errors": [
                            f"Line {e.line_number} [{e.record_type}] {e.field}: {e.issue}"
                            for e in result.validation_errors
                        ],
                        "corrected_file_content": result.corrected_file_content,
                        "corrected_lines": [
                            cl.model_dump() for cl in result.corrected_lines
                        ] if result.corrected_lines else None,
                    }
                    corrections_path.write_text(
                        json.dumps(corrections_data, indent=2), encoding="utf-8"
                    )
                except Exception as _cj_exc:  # noqa: BLE001
                    logger.warning("Could not write corrections JSON for %s: %s", path.name, _cj_exc)
                store.record_drop_file(
                    filename=path.name,
                    file_type="ccd",
                    outcome="under-review",
                    size_bytes=len(content),
                    detail=f"{len(result.validation_errors)} syntax error(s)",
                )
                store.append_event(
                    "BeforePaymentSubmissionAgent",
                    f"CCD file received — {path.name}: {len(result.validation_errors)} syntax "
                    "error(s) detected. File moved to under-review for correction.",
                )
        except Exception as exc:
            logger.error(
                "Scheduler [ccd_scanner]: failed to process %s — %s", path, exc
            )
            try:
                _move_unique(path, error_dir)
            except Exception:
                pass
            store.record_drop_file(
                filename=path.name,
                file_type="ccd",
                outcome="error",
                size_bytes=0,
                detail=str(exc),
            )
            store.append_event(
                "BeforePaymentSubmissionAgent",
                f"CCD file error — {path.name}: could not be parsed. {exc}",
            )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def _job_persist_store() -> None:
    """Flush the in-memory ledger to database_json/store.json if dirty."""
    from payment_tracking_agent.ledger import store as _store  # noqa: PLC0415
    _store.persist_if_dirty()


def start_scheduler() -> None:
    """Register jobs and start the APScheduler instance."""
    _scheduler.add_job(
        _job_scan_return_files,
        trigger=IntervalTrigger(seconds=settings.return_scan_interval_seconds),
        id="return_file_scanner",
        replace_existing=True,
        misfire_grace_time=10,
    )
    _scheduler.add_job(
        _job_push_to_scheme,
        trigger=IntervalTrigger(seconds=settings.scheme_push_interval_seconds),
        id="scheme_pusher",
        replace_existing=True,
        misfire_grace_time=10,
    )
    _scheduler.add_job(
        _job_scan_settlement_files,
        trigger=IntervalTrigger(seconds=settings.settlement_scan_interval_seconds),
        id="settlement_scanner",
        replace_existing=True,
        misfire_grace_time=10,
    )
    _scheduler.add_job(
        _job_scan_ccd_files,
        trigger=IntervalTrigger(seconds=settings.ccd_scan_interval_seconds),
        id="ccd_scanner",
        replace_existing=True,
        misfire_grace_time=10,
    )
    if settings.settlement_simulation_interval_seconds > 0:
        _scheduler.add_job(
            _job_simulate_settlement,
            trigger=IntervalTrigger(seconds=settings.settlement_simulation_interval_seconds),
            id="settlement_simulator",
            replace_existing=True,
            misfire_grace_time=10,
        )
    if settings.persist_interval_seconds > 0:
        _scheduler.add_job(
            _job_persist_store,
            trigger=IntervalTrigger(seconds=settings.persist_interval_seconds),
            id="store_persister",
            replace_existing=True,
            misfire_grace_time=30,
        )
    _scheduler.start()
    logger.info(
        "Scheduler started — ccd_scan=%ds  return_scan=%ds  scheme_push=%ds  "
        "settlement_scan=%ds  settlement_sim=%ds  persist=%ds",
        settings.ccd_scan_interval_seconds,
        settings.return_scan_interval_seconds,
        settings.scheme_push_interval_seconds,
        settings.settlement_scan_interval_seconds,
        settings.settlement_simulation_interval_seconds,
        settings.persist_interval_seconds,
    )


def stop_scheduler() -> None:
    """Gracefully stop the scheduler on application shutdown."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
