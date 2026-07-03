"""Syntax validator for ACH NACHA CCD fixed-width files.

Validates field-level rules for the record types that matter to the tracker:
  1  = File Header
  5  = Batch Header
  6  = Entry Detail

Returns a flat list of ``LineError`` objects — one per broken field.
An empty list means the file is syntactically valid.
"""

from __future__ import annotations

from dataclasses import dataclass

_RECORD_WIDTH = 94

# Valid NACHA transaction codes for credit/debit entries
_VALID_TRANSACTION_CODES = {
    "22", "23", "24",   # Checking: credit, pre-note credit, zero-dollar credit
    "27", "28", "29",   # Checking: debit,  pre-note debit,  zero-dollar debit
    "32", "33", "34",   # Savings:  credit, pre-note credit, zero-dollar credit
    "37", "38", "39",   # Savings:  debit,  pre-note debit,  zero-dollar debit
}

_VALID_SERVICE_CLASS_CODES = {"200", "220", "225"}


@dataclass
class LineError:
    """A single validation error tied to one line in the ACH file."""

    line_number: int   # 1-based
    record_type: str   # "1", "5", "6", etc.
    field: str         # NACHA field name
    issue: str         # Human-readable description of the problem
    raw_line: str      # The original line that triggered the error


# ---------------------------------------------------------------------------
# Per-record-type validators
# ---------------------------------------------------------------------------

def _is_digits(value: str) -> bool:
    return bool(value) and value.isdigit()


def _validate_file_header(line: str, line_number: int) -> list[LineError]:
    errors: list[LineError] = []

    priority_code = line[1:3]
    if priority_code != "01":
        errors.append(LineError(line_number, "1", "priority_code",
                                f"Expected '01', got '{priority_code}'", line))

    creation_date = line[23:29]
    if not _is_digits(creation_date):
        errors.append(LineError(line_number, "1", "file_creation_date",
                                f"Must be 6 digits (YYMMDD), got '{creation_date}'", line))

    record_size = line[34:37]
    if record_size != "094":
        errors.append(LineError(line_number, "1", "record_size",
                                f"Expected '094', got '{record_size}'", line))

    blocking_factor = line[37:39]
    if blocking_factor != "10":
        errors.append(LineError(line_number, "1", "blocking_factor",
                                f"Expected '10', got '{blocking_factor}'", line))

    format_code = line[39:40]
    if format_code != "1":
        errors.append(LineError(line_number, "1", "format_code",
                                f"Expected '1', got '{format_code}'", line))

    return errors


def _validate_batch_header(line: str, line_number: int) -> list[LineError]:
    errors: list[LineError] = []

    service_class = line[1:4]
    if service_class not in _VALID_SERVICE_CLASS_CODES:
        errors.append(LineError(line_number, "5", "service_class_code",
                                f"Must be one of {sorted(_VALID_SERVICE_CLASS_CODES)}, "
                                f"got '{service_class}'", line))

    effective_date = line[69:75]
    if not _is_digits(effective_date):
        errors.append(LineError(line_number, "5", "effective_entry_date",
                                f"Must be 6 digits (YYMMDD), got '{effective_date}'", line))

    odfi = line[79:87]
    if not _is_digits(odfi):
        errors.append(LineError(line_number, "5", "odfi_identification",
                                f"Must be 8 digits, got '{odfi}'", line))

    batch_number = line[87:94].strip()
    if not _is_digits(batch_number):
        errors.append(LineError(line_number, "5", "batch_number",
                                f"Must be numeric, got '{batch_number}'", line))

    return errors


def _validate_entry_detail(line: str, line_number: int) -> list[LineError]:
    errors: list[LineError] = []

    txn_code = line[1:3]
    if txn_code not in _VALID_TRANSACTION_CODES:
        errors.append(LineError(line_number, "6", "transaction_code",
                                f"Invalid transaction code '{txn_code}'. "
                                f"Valid codes: {sorted(_VALID_TRANSACTION_CODES)}", line))

    rdfi = line[3:11]
    if not _is_digits(rdfi):
        errors.append(LineError(line_number, "6", "receiving_dfi",
                                f"Must be 8 digits, got '{rdfi}'", line))

    check_digit = line[11:12]
    if not check_digit.isdigit():
        errors.append(LineError(line_number, "6", "check_digit",
                                f"Must be a single digit, got '{check_digit}'", line))

    amount = line[29:39]
    if not _is_digits(amount):
        errors.append(LineError(line_number, "6", "amount",
                                f"Must be 10 digits (in cents, zero-padded), got '{amount}'", line))

    # NACHA spec: addenda indicator at position 77 (0-based index 76)
    addenda_indicator = line[76:77]
    if addenda_indicator not in {"0", "1"}:
        errors.append(LineError(line_number, "6", "addenda_indicator",
                                f"Must be '0' or '1', got '{addenda_indicator}'", line))

    # NACHA spec: trace number at positions 78-94 (0-based indices 77-93), 17 chars
    trace = line[77:94]
    if not _is_digits(trace):
        errors.append(LineError(line_number, "6", "trace_number",
                                f"Must be 17 digits, got '{trace}'", line))

    return errors


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def validate_lines(raw_content: str) -> list[LineError]:
    """Validate every line of a raw NACHA ACH file string.

    Args:
        raw_content: Decoded text of the ACH file (ASCII).

    Returns:
        List of ``LineError`` objects.  An empty list means the file is valid.
    """
    errors: list[LineError] = []
    lines = raw_content.splitlines()

    for i, raw_line in enumerate(lines, start=1):
        stripped = raw_line.rstrip("\r\n,")  # strip newlines and CSV-export trailing commas

        # Skip blank lines and NACHA block-padding lines (all nines)
        if not stripped or set(stripped) == {"9"}:
            continue

        # --- Line-length check (must come before field checks) ---
        if len(stripped) != _RECORD_WIDTH:
            errors.append(LineError(
                i, stripped[0:1] or "?", "record_length",
                f"Expected {_RECORD_WIDTH} characters, got {len(stripped)}",
                stripped,
            ))
            continue  # Field positions are meaningless on a malformed-width line

        record_type = stripped[0]

        if record_type == "1":
            errors.extend(_validate_file_header(stripped, i))
        elif record_type == "5":
            errors.extend(_validate_batch_header(stripped, i))
        elif record_type == "6":
            errors.extend(_validate_entry_detail(stripped, i))
        # Record types 7, 8, 9 — recognised but not validated at field level here

    return errors
