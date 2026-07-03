"""Service to push validated CCD uploads to the ACH scheme folder.

Scans the in-memory upload store for files whose payments are still in
``WITH_BANK_UPLOADED`` status, copies the raw file to ``settings.scheme_dir``,
and advances every payment in that upload to ``WITH_SCHEME_SUBMITTED``
(business status: WITH SCHEME).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from payment_tracking_agent.config import settings
from payment_tracking_agent.ledger import store
from payment_tracking_agent.models.payment import PaymentStatus

logger = logging.getLogger(__name__)


def push_pending_uploads_to_scheme() -> list[str]:
    """Copy all pending uploads to the scheme directory and advance their status.

    A file is considered *pending* if every one of its entry detail records is
    still in ``WITH_BANK_UPLOADED`` status (i.e. it has not been sent yet).

    Returns:
        List of ``upload_id`` values that were successfully pushed.
    """
    scheme_dir = Path(settings.scheme_dir)
    scheme_dir.mkdir(parents=True, exist_ok=True)

    pushed_ids: list[str] = []

    for record in store.list_uploads():
        entries = [
            entry
            for batch in record.parsed.batches
            for entry in batch.entries
        ]
        if not entries:
            continue

        all_pending = all(
            e.status == PaymentStatus.WITH_BANK_UPLOADED for e in entries
        )
        if not all_pending:
            continue  # already pushed, or in a different state

        src = Path(record.file_path)
        if not src.exists():
            logger.warning(
                "Scheme push skipped — source file missing for upload %s: %s",
                record.upload_id,
                src,
            )
            continue

        dest = scheme_dir / src.name
        shutil.copy2(src, dest)

        store.update_all_payments_status(
            upload_id=record.upload_id,
            new_status=PaymentStatus.WITH_SCHEME_SUBMITTED,
        )
        pushed_ids.append(record.upload_id)
        store.append_event(
            "PaymentLifecycleOrchestrator",
            f"Scheme push \u2014 {record.file_name}: {len(entries)} payment(s) "
            "advanced to SENT TO SCHEME. File copied to scheme directory.",
        )
        logger.info(
            "Scheme push complete — upload=%s  dest=%s  payments=%d",
            record.upload_id,
            dest,
            len(entries),
        )

    return pushed_ids
