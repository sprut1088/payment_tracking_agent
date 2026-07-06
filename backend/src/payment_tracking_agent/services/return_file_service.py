"""Service for processing NACHA return files.

Parses the file, matches each return entry back to a stored payment by trace
number, updates the matched payment status to WITH_BENEFICIARY_BANK_PENDING
(business status: WITH BENEFICIARY BANK), and persists the result.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from payment_tracking_agent.agents import llm_fixer
from payment_tracking_agent.config import settings
from payment_tracking_agent.ledger import store
from payment_tracking_agent.models.payment import PaymentStatus
from payment_tracking_agent.models.return_file import (
    RETURN_REASON_DESCRIPTIONS,
    ProcessedReturnFile,
    ReturnRecord,
)
from payment_tracking_agent.parsers import return_file as return_parser

logger = logging.getLogger(__name__)


def process_return_file(file_name: str, content: bytes) -> ProcessedReturnFile:
    """Parse, match, and persist a NACHA return file.

    Pipeline:
      1. Parse type-6 / type-7 records to extract trace numbers and return codes.
      2. For each trace, look up the stored payment and advance its status to
         ``WITH_BENEFICIARY_BANK_PENDING`` (shown as "WITH BENEFICIARY BANK").
      3. Save the raw file to ``settings.return_dir``.
      4. Persist a ``ProcessedReturnFile`` summary to the in-memory store.

    Args:
        file_name: Original filename from the upload or file system scan.
        content:   Raw bytes of the NACHA return file.

    Returns:
        ``ProcessedReturnFile`` with per-record match results and counts.
    """
    raw_entries = return_parser.parse_return_bytes(content)

    # Persist raw file
    return_dir = Path(settings.return_dir)
    return_dir.mkdir(parents=True, exist_ok=True)
    return_file_id = str(uuid.uuid4())
    safe_name = f"{return_file_id}_{Path(file_name).name}"
    file_path = return_dir / safe_name
    file_path.write_bytes(content)

    records: list[ReturnRecord] = []
    matched_count = 0

    for entry in raw_entries:
        matched_upload_id: str | None = None
        matched = False

        upload_record, entry_record = store.find_payment_by_trace(entry.trace_number)
        if upload_record and entry_record:
            store.update_payment_status(
                upload_id=upload_record.upload_id,
                trace_number=entry.trace_number,
                new_status=PaymentStatus.REJECTED_BY_RETURN_FILE,
            )
            reason_desc = RETURN_REASON_DESCRIPTIONS.get(
                entry.return_reason_code, "Unknown return reason"
            )
            explanation = llm_fixer.explain_return_code(
                return_code=entry.return_reason_code,
                return_description=reason_desc,
                individual_name=entry.individual_name,
                amount=round(entry.amount_cents / 100.0, 2),
                receiving_dfi=entry_record.receiving_dfi,
                account_masked=entry_record.dfi_account_number_masked,
            )
            store.update_payment_return_info(
                upload_id=upload_record.upload_id,
                trace_number=entry.trace_number,
                return_reason_code=entry.return_reason_code,
                return_reason_description=reason_desc,
                customer_message=explanation["customer_message"],
                corrective_action=explanation["corrective_action"],
            )
            matched_upload_id = upload_record.upload_id
            matched = True
            matched_count += 1
            logger.info(
                "Return matched  trace=%s  reason=%s  upload=%s",
                entry.trace_number,
                entry.return_reason_code,
                upload_record.upload_id,
            )
        else:
            logger.warning("Return unmatched — trace not found: %s", entry.trace_number)

        records.append(
            ReturnRecord(
                trace_number=entry.trace_number,
                return_reason_code=entry.return_reason_code,
                return_reason_description=RETURN_REASON_DESCRIPTIONS.get(
                    entry.return_reason_code, "Unknown return reason"
                ),
                individual_name=entry.individual_name,
                amount_cents=entry.amount_cents,
                amount=round(entry.amount_cents / 100.0, 2),
                receiving_dfi=entry.receiving_dfi,
                matched_upload_id=matched_upload_id,
                matched=matched,
            )
        )

    result = ProcessedReturnFile(
        return_file_id=return_file_id,
        file_name=file_name,
        file_path=str(file_path),
        processed_at=datetime.now(tz=timezone.utc),
        return_records=records,
        matched_count=matched_count,
        unmatched_count=len(records) - matched_count,
    )
    store.save_return_file(result)
    if matched_count:
        store.append_event(
            "ReturnFileAgent",
            f"Return file processed \u2014 {file_name}: {matched_count} payment(s) matched "
            f"and advanced to REJECTED BY BENEFICIARY BANK. "
            f"{result.unmatched_count} unmatched trace(s).",
        )
    return result
