"""Deterministic NACHA ACH CCD record reconstructor.

When a line fails the 94-character length check, this module attempts to
reconstruct it with correct field widths using heuristic field extraction.

This is used as a post-processor after LLM suggestions: any corrected line
that is not exactly 94 chars gets replaced with the deterministic result.

Field widths per NACHA spec (all record types total 94 chars):
  Type 1 - File Header
  Type 5 - Batch Header
  Type 6 - Entry Detail
  Type 8 - Batch Control
  Type 9 - File Control
"""

from __future__ import annotations

import re


def reconstruct_record(raw: str) -> str:
    """Reconstruct a malformed NACHA record to exactly 94 characters.

    Returns a 94-char string.  If the record type is unrecognised or
    reconstruction raises an unexpected error the raw line is padded /
    truncated to 94 chars as a last resort.
    """
    raw = raw.rstrip("\r\n")
    if not raw:
        return " " * 94

    record_type = raw[0]
    try:
        dispatch = {"1": _fix_type1, "5": _fix_type5, "6": _fix_type6,
                    "8": _fix_type8, "9": _fix_type9}
        if record_type in dispatch:
            result = dispatch[record_type](raw)
        else:
            result = (raw + " " * 94)[:94]
    except Exception:
        result = (raw + " " * 94)[:94]

    # Hard guarantee
    return (result + " " * 94)[:94]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(raw: str, start: int, end: int, default: str = "") -> str:
    """Extract slice [start:end], padding with spaces if line is too short.

    Always returns exactly ``end - start`` characters.
    """
    width = end - start
    if len(raw) >= end:
        return raw[start:end]
    if len(raw) > start:
        partial = raw[start:]
        return (partial + " " * width)[:width]
    return (default + " " * width)[:width]


# ---------------------------------------------------------------------------
# Record-type fixers
# ---------------------------------------------------------------------------

def _fix_type1(raw: str) -> str:
    """Reconstruct File Header (type 1) to exactly 94 chars."""
    return (
        "1"
        + _get(raw, 1, 3, "01")       # Priority Code                 (2)
        + _get(raw, 3, 13, " " * 10)  # Immediate Destination         (10)
        + _get(raw, 13, 23, " " * 10) # Immediate Origin              (10)
        + _get(raw, 23, 29, " " * 6)  # File Creation Date            (6)
        + _get(raw, 29, 33, " " * 4)  # File Creation Time            (4)
        + _get(raw, 33, 34, "A")      # File ID Modifier              (1)
        + "094"                        # Record Size    — always 094   (3)
        + "10"                         # Blocking Factor — always 10   (2)
        + "1"                          # Format Code     — always 1    (1)
        + _get(raw, 40, 63, " " * 23) # Immediate Destination Name    (23)
        + _get(raw, 63, 86, " " * 23) # Immediate Origin Name         (23)
        + _get(raw, 86, 94, " " * 8)  # Reference Code                (8)
    )   # total = 1+2+10+10+6+4+1+3+2+1+23+23+8 = 94


def _fix_type5(raw: str) -> str:
    """Reconstruct Batch Header (type 5) to exactly 94 chars."""
    return (
        "5"
        + _get(raw, 1, 4, "200")       # Service Class Code            (3)
        + _get(raw, 4, 20, " " * 16)   # Company Name                  (16)
        + _get(raw, 20, 40, " " * 20)  # Company Discretionary Data    (20)
        + _get(raw, 40, 50, " " * 10)  # Company Identification        (10)
        + _get(raw, 50, 53, "CCD")     # Standard Entry Class Code     (3)
        + _get(raw, 53, 63, " " * 10)  # Company Entry Description     (10)
        + _get(raw, 63, 69, " " * 6)   # Company Descriptive Date      (6)
        + _get(raw, 69, 75, " " * 6)   # Effective Entry Date          (6)
        + _get(raw, 75, 78, "   ")     # Settlement Date (bank fills)  (3)
        + _get(raw, 78, 79, "1")       # Originator Status Code        (1)
        + _get(raw, 79, 87, " " * 8)   # ODFI Identification           (8)
        + _get(raw, 87, 94, "0000001") # Batch Number                  (7)
    )[:94]  # truncates if raw was longer than 94  (total = 94)


def _fix_type6(raw: str) -> str:
    """Reconstruct Entry Detail (type 6) to exactly 94 chars.

    Uses heuristic field extraction because the record is most commonly
    the one that is misaligned (short account / trace fields).
    """
    # Fixed-position prefix — reliable even on short lines
    transaction_code = _get(raw, 1, 3, "22")   # (2)
    rdfi             = _get(raw, 3, 11, "0" * 8)  # (8)
    check_digit      = _get(raw, 11, 12, "0")  # (1)
    rest = raw[12:] if len(raw) > 12 else ""

    # ---- Amount: 10 consecutive digits not part of a longer digit run -----
    amount_match = re.search(r"(?<!\d)(\d{10})(?!\d)", rest)
    if amount_match:
        amount      = amount_match.group(1)
        amount_pos  = amount_match.start()
    else:
        # Fallback: take any digit run, zero-pad to 10
        digit_match = re.search(r"\d+", rest)
        if digit_match:
            digs        = digit_match.group(0)
            amount      = digs.zfill(10)[:10]
            amount_pos  = digit_match.start()
        else:
            amount      = "0000000000"
            amount_pos  = 17  # assume standard account width

    # ---- DFI Account: content between pos 12 and amount ------------------
    account_raw = rest[:amount_pos].strip()
    account = account_raw.ljust(17)[:17]   # left-justified, space-padded (17)

    # ---- Fields after amount ---------------------------------------------
    after_amount   = rest[amount_pos + 10:]
    after_stripped = after_amount.rstrip()

    # Trace: last digit run at end of line (should be 17 digits)
    trace_match = re.search(r"(\d+)\s*$", after_stripped)
    if trace_match:
        trace_raw   = trace_match.group(1)
        trace       = trace_raw.zfill(17)[:17]   # zero-pad to 17 if short
        name_section = after_stripped[: trace_match.start()]
    else:
        trace        = "0" * 17
        name_section = after_stripped

    # Addenda indicator: always '0' for standard CCD (no addenda)
    addenda = "0"

    # Individual Name: up to 22 chars, left-justified, space-padded
    individual_name = name_section.strip()[:22].ljust(22)   # (22)

    # Individual ID Number: 15 chars (blank when not present)
    individual_id = " " * 15

    result = (
        "6"
        + transaction_code   # (2)
        + rdfi               # (8)
        + check_digit        # (1)
        + account            # (17)
        + amount             # (10)
        + individual_id      # (15)
        + individual_name    # (22)
        + addenda            # (1)
        + trace              # (17)
    )
    # 1+2+8+1+17+10+15+22+1+17 = 94
    return result


def _fix_type8(raw: str) -> str:
    """Reconstruct Batch Control (type 8) to exactly 94 chars."""
    return (
        "8"
        + _get(raw, 1, 4, "200")       # Service Class Code            (3)
        + _get(raw, 4, 10, "000000")   # Entry/Addenda Count           (6)
        + _get(raw, 10, 20, "0" * 10)  # Entry Hash                    (10)
        + _get(raw, 20, 32, "0" * 12)  # Total Debit Dollar Amount     (12)
        + _get(raw, 32, 44, "0" * 12)  # Total Credit Dollar Amount    (12)
        + _get(raw, 44, 54, " " * 10)  # Company Identification        (10)
        + _get(raw, 54, 73, " " * 19)  # Message Authentication Code   (19)
        + _get(raw, 73, 79, " " * 6)   # Reserved                      (6)
        + _get(raw, 79, 87, " " * 8)   # ODFI Identification           (8)
        + _get(raw, 87, 94, "0000001") # Batch Number                  (7)
    )[:94]  # truncate if raw was longer   (total = 94)


def _fix_type9(raw: str) -> str:
    """Reconstruct File Control (type 9) to exactly 94 chars."""
    return (
        "9"
        + _get(raw, 1, 7, "000001")    # Batch Count                   (6)
        + _get(raw, 7, 13, "000001")   # Block Count                   (6)
        + _get(raw, 13, 21, "00000020")# Entry/Addenda Count           (8)
        + _get(raw, 21, 31, "0" * 10)  # Entry Hash                    (10)
        + _get(raw, 31, 43, "0" * 12)  # Total Debit Dollar Amount     (12)
        + _get(raw, 43, 55, "0" * 12)  # Total Credit Dollar Amount    (12)
        + _get(raw, 55, 94, " " * 39)  # Reserved                      (39)
    )[:94]  # truncate if raw was longer   (total = 94)
