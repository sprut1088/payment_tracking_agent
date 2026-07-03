"""APScheduler background jobs for automated ACH processing.

Two recurring jobs:

1. ``return_file_scanner``
   Polls ``settings.return_scan_dir`` for new .ach / .txt files and passes each
   unprocessed file to ``return_file_service.process_return_file``.
   Matched payments are advanced to WITH_BENEFICIARY_BANK_PENDING.

2. ``scheme_pusher``
   Calls ``scheme_service.push_pending_uploads_to_scheme`` to copy any
   WITH_BANK_UPLOADED files to the scheme folder and advance their status to
   WITH_SCHEME_SUBMITTED.

Intervals are configured via ``settings.return_scan_interval_seconds`` and
``settings.scheme_push_interval_seconds`` (defaulting to 30 s each).
"""

from __future__ import annotations

import logging
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from payment_tracking_agent.config import settings

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler(timezone="UTC")


# ---------------------------------------------------------------------------
# Job implementations  (lazy imports to avoid circular dependencies)
# ---------------------------------------------------------------------------

def _job_scan_return_files() -> None:
    """Scan the return drop-folder and process any new files."""
    from payment_tracking_agent.ledger import store
    from payment_tracking_agent.services import return_file_service

    scan_dir = Path(settings.return_scan_dir)
    if not scan_dir.exists():
        return

    already_processed: set[str] = {r.file_path for r in store.list_return_files()}

    ach_files = sorted(scan_dir.glob("*.ach"))
    txt_files = sorted(scan_dir.glob("*.txt"))

    for path in ach_files + txt_files:
        if str(path) in already_processed:
            continue
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
        except Exception as exc:
            logger.error(
                "Scheduler [return_file_scanner]: failed to process %s — %s",
                path,
                exc,
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


def _job_scan_settlement_files() -> None:
    """Scan the settlement drop-folder and process any new files."""
    from payment_tracking_agent.ledger import store
    from payment_tracking_agent.services import settlement_service

    scan_dir = Path(settings.settlement_scan_dir)
    if not scan_dir.exists():
        return

    already_processed: set[str] = {r.file_path for r in store.list_settlement_files()}

    csv_files = sorted(scan_dir.glob("*.csv"))
    txt_files = sorted(scan_dir.glob("*.txt"))
    dat_files = sorted(scan_dir.glob("*.dat"))

    for path in csv_files + txt_files + dat_files:
        if str(path) in already_processed:
            continue
        logger.info("Scheduler [settlement_scanner]: processing %s", path.name)
        try:
            content = path.read_bytes()
            result = settlement_service.process_settlement_file(path.name, content)
            logger.info(
                "Scheduler [settlement_scanner]: %s — matched=%d unmatched=%d",
                path.name,
                result.matched_count,
                result.unmatched_count,
            )
        except Exception as exc:
            logger.error(
                "Scheduler [settlement_scanner]: failed to process %s — %s", path, exc
            )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

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
    _scheduler.start()
    logger.info(
        "Scheduler started — return_scan=%ds  scheme_push=%ds  settlement_scan=%ds",
        settings.return_scan_interval_seconds,
        settings.scheme_push_interval_seconds,
        settings.settlement_scan_interval_seconds,
    )


def stop_scheduler() -> None:
    """Gracefully stop the scheduler on application shutdown."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
