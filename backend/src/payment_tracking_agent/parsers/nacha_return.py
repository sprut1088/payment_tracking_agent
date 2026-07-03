"""NACHA return addenda parser (Prompt 11).

Reads record type 7 addenda type 99 rows from a NACHA return file using the
fixed-width position map from ``.github/copilot-instructions.md``. Non-addenda
rows are ignored. This module intentionally does not implement full NACHA
return parsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_ADDENDA_RECORD_LENGTH = 94
_RECORD_TYPE = slice(0, 1)
_ADDENDA_TYPE = slice(1, 3)
_RETURN_REASON = slice(3, 6)
_ORIGINAL_TRACE = slice(6, 21)
_TRACE_NUMBER = slice(79, 94)


@dataclass(frozen=True)
class ParsedReturnAddenda:
    """One type 7 addenda type 99 row from a NACHA return file."""

    record_type_code: str
    addenda_type_code: str
    return_reason_code: str
    original_trace_number: str
    trace_number: str


@dataclass
class ParsedReturnFile:
    """Result of parsing a NACHA return file."""

    source_file: str
    addenda: list[ParsedReturnAddenda] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_return_file(path: Path) -> ParsedReturnFile:
    """Parse a NACHA return file for type 7 addenda type 99 records only.

    Lines are treated as fixed-width. Only line endings are removed before
    slicing so field positions stay aligned to the NACHA column map.
    """
    result = ParsedReturnFile(source_file=path.name)
    text = path.read_text(encoding="utf-8", errors="replace")

    for line_no, raw_line in enumerate(text.split("\n"), start=1):
        raw = raw_line.rstrip("\r\n")
        if not raw:
            continue
        if raw[_RECORD_TYPE] != "7":
            continue
        if len(raw) != _ADDENDA_RECORD_LENGTH:
            result.errors.append(
                f"line {line_no}: addenda is {len(raw)} chars, expected {_ADDENDA_RECORD_LENGTH}"
            )
            continue
        if raw[_ADDENDA_TYPE] != "99":
            continue
        result.addenda.append(
            ParsedReturnAddenda(
                record_type_code=raw[_RECORD_TYPE],
                addenda_type_code=raw[_ADDENDA_TYPE],
                return_reason_code=raw[_RETURN_REASON].rstrip(),
                original_trace_number=raw[_ORIGINAL_TRACE].rstrip(),
                trace_number=raw[_TRACE_NUMBER].rstrip(),
            )
        )

    return result
