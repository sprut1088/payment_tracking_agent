"""Settlement rejection file parser.

Supported formats
-----------------

**Format A — Segmented (FedACH-style)**

  Record type ``10`` = file header (optional, skipped)
  Record type ``20`` = rejection detail record
  Record type ``30`` = file trailer (optional, skipped)

  Detail record layout (pipe-delimited fields after the type code):
    20|<trace_number>|<reason_code>|<reason_text>

  Example::

    10|SETTLEMENT REJECTION|20260702|CYCLE100002
    20|000000010000001|R02|Account Closed
    20|000000010000002|R03|No Account Found
    30|2

**Format B — Header-less pipe-delimited**

  Lines that do not start with a known segment code are parsed as::

    <trace_number>|<reason_code>|<reason_text>

  Example::

    000000010000001|R02|Account Closed
    000000010000002|R03|No Account Found

Both formats can be mixed within the same file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_REASON_CODE_RE = re.compile(r"\bR\d{2}\b")


@dataclass
class RawRejectionEntry:
    trace_number: str
    reason_code: str
    reason_text: str


def _clean(value: str) -> str:
    return value.strip()


def _try_parse_detail_line(line: str) -> RawRejectionEntry | None:
    """Attempt to parse a single line as a rejection record.

    Supports:
      - ``20|trace|code|text``          (segmented format)
      - ``trace|code|text``             (headerless pipe-delimited)
      - ``trace  code  text``           (whitespace-separated)
    """
    parts = [_clean(p) for p in line.split("|")]

    # Segmented: leading "20" type code
    if parts[0] == "20" and len(parts) >= 4:
        return RawRejectionEntry(
            trace_number=parts[1],
            reason_code=parts[2],
            reason_text="|".join(parts[3:]),
        )

    # Skip known non-data segment codes
    if parts[0] in {"10", "30"}:
        return None

    # Headerless: 3+ pipe-separated fields where field[1] looks like R-code
    if len(parts) >= 3 and _REASON_CODE_RE.match(parts[1]):
        return RawRejectionEntry(
            trace_number=parts[0],
            reason_code=parts[1],
            reason_text="|".join(parts[2:]),
        )

    # Whitespace-separated fallback: "trace  R02  reason text"
    tokens = line.split(None, 2)
    if len(tokens) >= 2 and _REASON_CODE_RE.match(tokens[1]):
        return RawRejectionEntry(
            trace_number=tokens[0],
            reason_code=tokens[1],
            reason_text=tokens[2] if len(tokens) > 2 else "",
        )

    return None


def parse_settlement_bytes(content: bytes) -> list[RawRejectionEntry]:
    """Parse raw settlement file bytes into a list of rejection entries.

    Args:
        content: Raw file bytes (UTF-8 or ASCII).

    Returns:
        List of ``RawRejectionEntry`` objects.  Empty list if no data lines found.
    """
    text = content.decode("utf-8", errors="replace")
    entries: list[RawRejectionEntry] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue  # skip blank lines and comments
        entry = _try_parse_detail_line(line)
        if entry:
            entries.append(entry)

    return entries
