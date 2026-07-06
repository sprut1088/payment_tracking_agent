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

        # ── Pre-submission risk validation ────────────────────────────
        hold_traces: set[str] = set()
        review_traces: set[str] = set()
        validation_ok = False
        try:
            from payment_tracking_agent.services import pre_submission_service  # noqa: PLC0415

            store.append_event(
                "BeforePaymentSubmissionAgent",
                f"Pre-submission validation starting — {record.file_name}: "
                f"checking {len(entries)} payment(s) against historical rejection records "
                "and AI risk signals before scheme submission.",
            )

            validation = pre_submission_service.validate_batch_before_submission(record)
            store.save_pre_submission_result(validation)
            validation_ok = True

            # Build per-trace action map so we can route payments individually
            for pa in validation.payment_assessments:
                if pa.action == "HOLD":
                    hold_traces.add(pa.trace_number)
                elif pa.action == "REVIEW":
                    review_traces.add(pa.trace_number)

            risk_summary = (
                f"batch risk={validation.batch_risk_level} "
                f"hold={validation.hold_count} review={validation.review_count} "
                f"proceed={validation.proceed_count}"
            )
            status_label = (
                "HOLD" if validation.hold_count
                else "REVIEW" if validation.review_count
                else "PROCEED"
            )
            store.append_event(
                "BeforePaymentSubmissionAgent",
                f"Pre-submission validation complete — {record.file_name}: "
                f"decision={status_label}. {validation.ai_batch_summary} ({risk_summary})",
            )
            logger.info(
                "Pre-submission validation — upload=%s %s",
                record.upload_id, risk_summary,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Pre-submission validation failed for %s — batch will not be sent to scheme: %s",
                record.upload_id, exc, exc_info=True,
            )
            store.append_event(
                "BeforePaymentSubmissionAgent",
                f"Pre-submission validation FAILED — {record.file_name}: {exc}. "
                "Batch withheld from scheme. Will retry on next cycle.",
            )

        if not validation_ok:
            # Do not send to scheme if validation could not complete.
            # The batch stays WITH_BANK_UPLOADED and will be retried next tick.
            continue

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

        # Apply per-payment routing based on validation action.
        # ACH batches are submitted as a unit — if ANY payment is HOLD or REVIEW,
        # the entire batch is held back so operators can verify before submission.
        if hold_traces or review_traces:
            # Hold the whole batch
            store.update_all_payments_status(
                upload_id=record.upload_id,
                new_status=PaymentStatus.WITH_BANK_VALIDATION_FAILED,
            )
            reason = "HOLD" if hold_traces else "REVIEW"
            flagged = len(hold_traces) or len(review_traces)
            store.append_event(
                "BeforePaymentSubmissionAgent",
                f"Batch {reason} — {record.file_name}: {flagged} payment(s) flagged "
                f"{reason} by pre-submission validation. Entire batch of {len(entries)} "
                "payment(s) kept WITH BANK. Review on Batch Dashboard before resubmission.",
            )
            logger.info(
                "Scheme push BLOCKED (%s) — upload=%s  flagged=%d  total=%d",
                reason, record.upload_id, flagged, len(entries),
            )
            # Do NOT add to pushed_ids — batch was not sent
        else:
            # All PROCEED or REVIEW — advance entire batch to scheme
            store.update_all_payments_status(
                upload_id=record.upload_id,
                new_status=PaymentStatus.WITH_SCHEME_SUBMITTED,
            )
            pushed_ids.append(record.upload_id)
            if review_traces:
                store.append_event(
                    "BeforePaymentSubmissionAgent",
                    f"Scheme push — {record.file_name}: {len(entries)} payment(s) sent to scheme. "
                    f"{len(review_traces)} payment(s) flagged REVIEW — monitor for returns.",
                )
            else:
                store.append_event(
                    "PaymentLifecycleOrchestrator",
                    f"Scheme push \u2014 {record.file_name}: {len(entries)} payment(s) "
                    "advanced to SENT TO SCHEME. File copied to scheme directory.",
                )
            logger.info(
                "Scheme push complete — upload=%s  dest=%s  payments=%d  review=%d",
                record.upload_id, dest, len(entries), len(review_traces),
            )

    return pushed_ids
