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

**Format C — FedACH Fixed-Width Summary**

  Fixed-width records with no pipe delimiters.  Used by FedACH settlement
  summary reports.  No individual trace numbers or rejection codes are
  present — this file is summary-level evidence that the batch settled.

  Record type ``10`` = file header::

    10[identifier(8)][date YYYYMMDD(8)][time HHMMSS(6)][participant(1)][routing(8)][desc...]

  Record type ``20`` = category summary detail::

    20[category(4)][count(6)][amount(14)][indicator C/D(1)]

  Record type ``30`` = file trailer::

    30[item_count(8)][debit_amount(12)][debit_indicator(1)]
       [credit_amount(12)][credit_indicator(1)][...]

  Example::

    10FACTRNSM20260702170000112345678FEDACH CCD 17:00
    20FWDC00000200000000067500C
    30000000200000000000000D00000000067500C00000000067500C

Both formats A/B can be mixed within the same file.
Format C is detected automatically when no pipe delimiters are found
alongside type-10/20/30 records.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from payment_tracking_agent.models.settlement import FedAchSummary

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


# ---------------------------------------------------------------------------
# FedACH fixed-width summary parser (Format C)
# ---------------------------------------------------------------------------

def _parse_fedach_summary(lines: list[str]) -> FedAchSummary | None:
    """Try to extract FedACH settlement summary metadata from type-10/20/30 records.

    Only activates when NO pipe delimiters are found in the file — i.e., this
    is a fixed-width summary file, not a rejection file.

    Record layout:
      10[id(8)][date YYYYMMDD(8)][time HHMMSS(6)][participant(1)][routing(8)][desc...]
      20[category(4)][count(6)][amount(14)][indicator(1)]
      30[item_count(8)][...]
    """
    # Only apply when there are no pipes anywhere in the file
    if any("|" in line for line in lines):
        return None

    header = next((ln for ln in lines if ln.startswith("10")), None)
    detail = next((ln for ln in lines if ln.startswith("20")), None)
    trailer = next((ln for ln in lines if ln.startswith("30")), None)

    # Require at least one detail record with the expected fixed-width shape
    if not detail or len(detail) < 6:
        return None

    summary = FedAchSummary()

    # ── Record 10 — file header ──────────────────────────────────────────
    # 10 [id:8] [date:8] [time:6] [participant:1] [routing:8] [desc...]
    if header and len(header) >= 24:
        summary.settlement_date = header[10:18].strip()   # YYYYMMDD
        summary.settlement_time = header[18:24].strip()   # HHMMSS
        if len(header) >= 33:
            summary.routing_number = header[25:33].strip()
        if len(header) > 33:
            summary.description = header[33:].strip()

    # ── Record 20 — category detail ──────────────────────────────────────
    # 20 [category:4] [count:6] [amount:14] [indicator:1]
    if len(detail) >= 12:
        summary.category = detail[2:6].strip()
        try:
            summary.item_count = int(detail[6:12]) if detail[6:12].strip() else 0
        except ValueError:
            pass
    if len(detail) >= 27:
        try:
            summary.gross_amount_cents = int(detail[12:26])
        except ValueError:
            pass
        if detail[26] in "CD":
            summary.net_indicator = detail[26]

    # ── Record 30 — trailer (item count is more reliable here) ───────────
    # 30 [item_count:8] [...]
    if trailer and len(trailer) >= 10:
        try:
            trailer_count = int(trailer[2:10])
            if trailer_count > 0:
                summary.item_count = trailer_count  # prefer trailer total
        except ValueError:
            pass

    return summary


def parse_settlement_bytes(content: bytes) -> tuple[list[RawRejectionEntry], FedAchSummary | None]:
    """Parse raw settlement file bytes.

    Args:
        content: Raw file bytes (UTF-8 or ASCII).

    Returns:
        A tuple of:
        - List of ``RawRejectionEntry`` objects (empty for pure summary files).
        - ``FedAchSummary`` when the file is a FedACH fixed-width summary,
          or ``None`` for pipe-delimited rejection files.
    """
    text = content.decode("utf-8", errors="replace")
    raw_lines = [ln.strip() for ln in text.splitlines()]
    non_empty = [ln for ln in raw_lines if ln and not ln.startswith("#")]

    fed_ach_summary = _parse_fedach_summary(non_empty)

    entries: list[RawRejectionEntry] = []
    for line in non_empty:
        entry = _try_parse_detail_line(line)
        if entry:
            entries.append(entry)

    return entries, fed_ach_summary

