"""NACHA return file parser.

Handles two variants:

1. **Standard NACHA** — type-6 entry followed by type-7 addenda (addenda type "99").
   The addenda record carries the return reason code and original trace number.

2. **Simplified / mock** — return reason code (R\\d\\d) is embedded directly in the
   individual name field of the type-6 record (as in the demo sample files).

In both cases the output is a list of ``RawReturnEntry`` objects keyed by the
original trace number so the service can match them back to stored payments.

Sample return file layout (simplified):
  101 987654321 1234567892607021800A094101RDFI BANK              ODFI BANK
  5200RETURN PROCESSING  ...
  6270210000211000000000000005   0000020000VENDOR 05             R02ACCTCLOSED0000001
  6270210000211000000000000011   0000035000VENDOR 11             R03NOACCOUNT 0000002
  820000000200042000055000000550009876543210 ...
  9000001000001...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_RECORD_WIDTH = 94
_RETURN_CODE_RE = re.compile(r"R\d{2}")


@dataclass
class RawReturnEntry:
    """Intermediate parsed representation of one returned payment."""

    trace_number: str
    individual_name: str
    amount_cents: int
    receiving_dfi: str
    return_reason_code: str = field(default="")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pad(line: str) -> str:
    return line.ljust(_RECORD_WIDTH)


def _extract_code_from_field(text: str) -> str:
    """Scan *text* for an R-code pattern (R01 … R99). Returns '' if not found."""
    m = _RETURN_CODE_RE.search(text)
    return m.group(0) if m else ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_return_bytes(content: bytes) -> list[RawReturnEntry]:
    """Parse the raw bytes of a NACHA return file.

    Args:
        content: Raw file bytes (ASCII).

    Returns:
        List of ``RawReturnEntry`` objects, one per returned payment entry.
        The ``return_reason_code`` field may be empty for unknown/malformed files.
    """
    text = content.decode("ascii", errors="replace")
    lines = [_pad(ln) for ln in text.splitlines() if ln.strip()]

    entries: list[RawReturnEntry] = []
    pending: RawReturnEntry | None = None

    for line in lines:
        record_type = line[0]

        if record_type == "6":
            # Flush any previously open entry that had no addenda record
            if pending is not None:
                if not pending.return_reason_code:
                    # Fallback: scan individual name field for an embedded R-code
                    pending.return_reason_code = _extract_code_from_field(
                        pending.individual_name
                    )
                entries.append(pending)

            amount_raw = line[29:39].strip()
            amount_cents = int(amount_raw) if amount_raw.isdigit() else 0

            pending = RawReturnEntry(
                trace_number=line[79:94].strip(),
                individual_name=line[54:76].strip(),
                amount_cents=amount_cents,
                receiving_dfi=line[3:11].strip(),
            )

        elif record_type == "7" and pending is not None:
            addenda_type = line[1:3]
            if addenda_type == "99":
                # Standard NACHA return addenda (type 99)
                # [3:6]   = Return Reason Code
                # [6:21]  = Original Entry Trace Number
                reason = line[3:6].strip()
                original_trace = line[6:21].strip()
                pending.return_reason_code = reason
                if original_trace:
                    pending.trace_number = original_trace  # prefer addenda trace
            else:
                # Non-99 addenda — try to find an R-code anywhere in the record
                pending.return_reason_code = _extract_code_from_field(line)

            entries.append(pending)
            pending = None

        elif record_type in {"8", "9"}:
            # Batch / file control — flush pending entry
            if pending is not None:
                if not pending.return_reason_code:
                    pending.return_reason_code = _extract_code_from_field(
                        pending.individual_name
                    )
                entries.append(pending)
                pending = None

    # Guard: flush any entry that was never closed
    if pending is not None:
        if not pending.return_reason_code:
            pending.return_reason_code = _extract_code_from_field(
                pending.individual_name
            )
        entries.append(pending)

    return entries
