"""Service for processing settlement rejection files.

Pipeline
--------
1. Parse the file to extract ``(trace_number, reason_code, reason_text)`` records.
2. Deduplicate reason codes and call the LLM advisor *once* (batched) to get
   corrective action guidance for each unique rejection reason.
3. For every parsed record:
   a. Look up the payment by trace number in the in-memory store.
   b. Advance matched payment status to ``REJECTED_BY_SETTLEMENT``.
   c. Attach the LLM-suggested corrective action to the payment record.
4. Save the raw file to ``settings.settlement_dir``.
5. Persist a ``ProcessedSettlementFile`` summary to the store.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from payment_tracking_agent.agents import llm_advisor
from payment_tracking_agent.config import settings
from payment_tracking_agent.ledger import store
from payment_tracking_agent.models.payment import PaymentStatus
from payment_tracking_agent.models.return_file import RETURN_REASON_DESCRIPTIONS
from payment_tracking_agent.models.settlement import ProcessedSettlementFile, RejectionRecord
from payment_tracking_agent.parsers import settlement as settlement_parser

logger = logging.getLogger(__name__)


def process_settlement_file(file_name: str, content: bytes) -> ProcessedSettlementFile:
    """Parse, enrich with LLM guidance, match payments, and persist a settlement file.

    Args:
        file_name: Original filename from the upload or file-system scan.
        content:   Raw bytes of the settlement rejection file.

    Returns:
        ``ProcessedSettlementFile`` with per-record match results and LLM actions.
    """
    raw_entries = settlement_parser.parse_settlement_bytes(content)

    # ------------------------------------------------------------------
    # Step 1: Deduplicate reason codes → single batched LLM call
    # ------------------------------------------------------------------
    seen_codes: dict[str, str] = {}  # reason_code → reason_text
    for entry in raw_entries:
        if entry.reason_code and entry.reason_code not in seen_codes:
            # Prefer explicit reason_text from file; fall back to NACHA descriptions
            text = entry.reason_text or RETURN_REASON_DESCRIPTIONS.get(
                entry.reason_code, entry.reason_code
            )
            seen_codes[entry.reason_code] = text

    corrective_actions: dict[str, str] = llm_advisor.get_corrective_actions(
        list(seen_codes.items())
    )
    logger.info(
        "Settlement LLM advisor: %d unique reason codes → %d suggestions",
        len(seen_codes),
        len(corrective_actions),
    )

    # ------------------------------------------------------------------
    # Step 2: Save raw file to settlement directory
    # ------------------------------------------------------------------
    settlement_dir = Path(settings.settlement_dir)
    settlement_dir.mkdir(parents=True, exist_ok=True)
    settlement_file_id = str(uuid.uuid4())
    safe_name = f"{settlement_file_id}_{Path(file_name).name}"
    file_path = settlement_dir / safe_name
    file_path.write_bytes(content)

    # ------------------------------------------------------------------
    # Step 3: Match traces, update statuses, attach LLM action
    # ------------------------------------------------------------------
    records: list[RejectionRecord] = []
    matched_count = 0

    for entry in raw_entries:
        matched_upload_id: str | None = None
        matched = False

        upload_record, entry_record = store.find_payment_by_trace(entry.trace_number)
        action = corrective_actions.get(
            entry.reason_code,
            RETURN_REASON_DESCRIPTIONS.get(entry.reason_code, "No suggestion available."),
        )

        if upload_record and entry_record:
            # Advance payment to REJECTED status
            store.update_payment_status(
                upload_id=upload_record.upload_id,
                trace_number=entry.trace_number,
                new_status=PaymentStatus.REJECTED_BY_SETTLEMENT,
            )
            # Attach the corrective action to the payment record itself
            store.set_payment_corrective_action(
                upload_id=upload_record.upload_id,
                trace_number=entry.trace_number,
                action=action,
            )
            matched_upload_id = upload_record.upload_id
            matched = True
            matched_count += 1
            logger.info(
                "Settlement matched  trace=%s  reason=%s  upload=%s",
                entry.trace_number,
                entry.reason_code,
                upload_record.upload_id,
            )
        else:
            logger.warning(
                "Settlement unmatched — trace not found: %s", entry.trace_number
            )

        records.append(
            RejectionRecord(
                trace_number=entry.trace_number,
                reason_code=entry.reason_code,
                reason_text=entry.reason_text
                or RETURN_REASON_DESCRIPTIONS.get(entry.reason_code, ""),
                llm_suggested_action=action,
                matched_upload_id=matched_upload_id,
                matched=matched,
            )
        )

    result = ProcessedSettlementFile(
        settlement_file_id=settlement_file_id,
        file_name=file_name,
        file_path=str(file_path),
        processed_at=datetime.now(tz=timezone.utc),
        rejection_records=records,
        matched_count=matched_count,
        unmatched_count=len(records) - matched_count,
        reason_codes_seen=list(seen_codes.keys()),
    )
    store.save_settlement_file(result)
    return result
