"""ACH CCD parser (Prompt 09).

Parses record type 6 entry detail rows from a NACHA CCD file using the
fixed-width position map from ``.github/copilot-instructions.md``. This module
only handles CCD structural parsing; it does not evaluate settlement,
scheme-reject, or return evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# NACHA record type 6 entry detail slice map (1-indexed positions from the
# prompt spec, converted to Python half-open slices).
_ENTRY_DETAIL_LENGTH = 94
_RECORD_TYPE = slice(0, 1)
_TRANSACTION_CODE = slice(1, 3)
_RECEIVING_DFI = slice(3, 11)
_CHECK_DIGIT = slice(11, 12)
_ACCOUNT_NUMBER = slice(12, 29)
_AMOUNT = slice(29, 39)
_INDIVIDUAL_ID = slice(39, 54)
_INDIVIDUAL_NAME = slice(54, 76)
_DISCRETIONARY = slice(76, 78)
_ADDENDA_INDICATOR = slice(78, 79)
_TRACE_NUMBER = slice(79, 94)


@dataclass(frozen=True)
class ParsedCcdEntry:
    """A single record type 6 entry detail row."""

    record_type_code: str
    transaction_code: str
    receiving_dfi_identification: str
    check_digit: str
    dfi_account_number: str
    amount_cents: int
    individual_id_number: str
    individual_name: str
    discretionary_data: str
    addenda_record_indicator: str
    trace_number: str


@dataclass
class ParsedCcdFile:
    """Result of parsing a CCD file."""

    source_file: str
    entries: list[ParsedCcdEntry] = field(default_factory=list)
    syntax_valid: bool = True
    errors: list[str] = field(default_factory=list)


def mask_account_number(account: str) -> str:
    """Return a masked account number safe for API responses.

    Keeps the last 4 characters visible and replaces the rest with ``*``.
    """
    cleaned = account.strip()
    if len(cleaned) <= 4:
        return "*" * len(cleaned)
    return "*" * (len(cleaned) - 4) + cleaned[-4:]


def parse_ccd_file(path: Path) -> ParsedCcdFile:
    """Parse a CCD file and return its type 6 entry detail rows.

    Non-fatal syntax problems (short lines, non-numeric amounts) are recorded
    on ``errors`` and set ``syntax_valid`` to False. Rows that can still be
    interpreted are returned so downstream code can classify affected payments
    as ``WITH BANK`` per the SME lifecycle.

    Lines are treated as fixed-width. Only line endings are removed before
    slicing; the parser does not otherwise strip whitespace at the line level
    so field positions stay aligned to the NACHA column map.
    """
    result = ParsedCcdFile(source_file=path.name)
    text = path.read_text(encoding="utf-8", errors="replace")

    for line_no, raw_line in enumerate(text.split("\n"), start=1):
        raw = raw_line.rstrip("\r\n")
        if not raw:
            continue
        if raw[_RECORD_TYPE] != "6":
            continue

        if len(raw) != _ENTRY_DETAIL_LENGTH:
            result.syntax_valid = False
            result.errors.append(
                f"line {line_no}: entry detail is {len(raw)} chars, expected {_ENTRY_DETAIL_LENGTH}"
            )
            continue

        amount_raw = raw[_AMOUNT]
        try:
            amount_cents = int(amount_raw)
        except ValueError:
            result.syntax_valid = False
            result.errors.append(
                f"line {line_no}: amount field {amount_raw!r} is not numeric"
            )
            continue

        result.entries.append(
            ParsedCcdEntry(
                record_type_code=raw[_RECORD_TYPE],
                transaction_code=raw[_TRANSACTION_CODE],
                receiving_dfi_identification=raw[_RECEIVING_DFI],
                check_digit=raw[_CHECK_DIGIT],
                dfi_account_number=raw[_ACCOUNT_NUMBER].rstrip(),
                amount_cents=amount_cents,
                individual_id_number=raw[_INDIVIDUAL_ID].rstrip(),
                individual_name=raw[_INDIVIDUAL_NAME].rstrip(),
                discretionary_data=raw[_DISCRETIONARY],
                addenda_record_indicator=raw[_ADDENDA_INDICATOR],
                trace_number=raw[_TRACE_NUMBER].rstrip(),
            )
        )

    return result
