"""Reader for the demo scheme-reject JSON fixture (Prompt 10).

This is not a full ACH/PEP+ format parser. It reads the demo JSON shape
described in ``.github/copilot-instructions.md`` and returns typed records so
the ledger can update the affected payments deterministically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SchemeRejectRecord:
    """One rejected payment described by a scheme-reject file."""

    trace_number: str
    customer_id: str = ""
    customer_name: str = ""
    amount: float | None = None
    reason_code: str = ""
    reason: str = ""
    recommended_action: str = ""


@dataclass
class SchemeRejectFile:
    """Parsed scheme-reject file contents."""

    source_file: str
    batch_id: str = ""
    records: list[SchemeRejectRecord] = field(default_factory=list)


def parse_scheme_reject_file(path: Path) -> SchemeRejectFile:
    """Read a demo scheme-reject JSON file into typed records.

    Unknown or missing fields are tolerated; the trace number is the only
    strictly required key on each rejection because ledger matching uses it.
    Rejections without a trace number are skipped.
    """
    result = SchemeRejectFile(source_file=path.name)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return result

    if not isinstance(payload, dict):
        return result

    batch_id = payload.get("batch_id")
    if isinstance(batch_id, str):
        result.batch_id = batch_id

    for raw in payload.get("rejections", []) or []:
        if not isinstance(raw, dict):
            continue
        trace = raw.get("payment_trace_number") or raw.get("trace_number")
        if not isinstance(trace, str) or not trace.strip():
            continue
        amount = raw.get("amount")
        if amount is not None and not isinstance(amount, (int, float)):
            amount = None
        result.records.append(
            SchemeRejectRecord(
                trace_number=trace.strip(),
                customer_id=str(raw.get("customer_id") or ""),
                customer_name=str(raw.get("customer_name") or ""),
                amount=float(amount) if amount is not None else None,
                reason_code=str(raw.get("reason_code") or ""),
                reason=str(raw.get("reason") or ""),
                recommended_action=str(raw.get("recommended_action") or ""),
            )
        )
    return result
