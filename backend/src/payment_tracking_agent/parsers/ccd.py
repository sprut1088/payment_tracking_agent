"""ACH CCD fixed-width file parser.

NACHA ACH file format — every record is exactly 94 characters wide.

Record types parsed:
  1  = File Header
  5  = Batch Header
  6  = Entry Detail (one per payment)
  7  = Addenda (recognised, not stored)
  8  = Batch Control (closes the current batch)
  9  = File Control (end of file)
"""

from __future__ import annotations

from payment_tracking_agent.models.payment import (
    BatchHeaderRecord,
    EntryDetailRecord,
    FileHeaderRecord,
    ParsedBatch,
    ParsedCCDFile,
)

_RECORD_WIDTH = 94


def _pad(line: str) -> str:
    """Ensure line is at least 94 characters (handles short/truncated lines)."""
    return line.ljust(_RECORD_WIDTH)


def _mask_account(raw: str) -> str:
    """Mask all but the last 4 characters of an account number."""
    value = raw.strip()
    if len(value) <= 4:
        return value
    return "*" * (len(value) - 4) + value[-4:]


# ---------------------------------------------------------------------------
# Record-level parsers
# ---------------------------------------------------------------------------

def _parse_file_header(line: str) -> FileHeaderRecord:
    """Record type 1 — File Header (positions are 1-based in NACHA spec; 0-based here)."""
    return FileHeaderRecord(
        immediate_destination=line[3:13].strip(),
        immediate_origin=line[13:23].strip(),
        file_creation_date=line[23:29].strip(),
        file_creation_time=line[29:33].strip(),
        file_id_modifier=line[33:34].strip(),
        immediate_destination_name=line[40:63].strip(),
        immediate_origin_name=line[63:86].strip(),
    )


def _parse_batch_header(line: str) -> BatchHeaderRecord:
    """Record type 5 — Batch Header."""
    return BatchHeaderRecord(
        service_class_code=line[1:4].strip(),
        company_name=line[4:20].strip(),
        company_identification=line[40:50].strip(),
        sec_code=line[50:53].strip(),
        company_entry_description=line[53:63].strip(),
        effective_entry_date=line[69:75].strip(),
        odfi_identification=line[79:87].strip(),
        batch_number=line[87:94].strip(),
    )


def _parse_entry_detail(
    line: str, batch_number: str, sec_code: str
) -> EntryDetailRecord:
    """Record type 6 — Entry Detail (one tracked payment)."""
    amount_raw = line[29:39]
    amount_cents = int(amount_raw) if amount_raw.strip().isdigit() else 0

    return EntryDetailRecord(
        transaction_code=line[1:3].strip(),
        receiving_dfi=line[3:11].strip(),
        check_digit=line[11:12].strip(),
        dfi_account_number_masked=_mask_account(line[12:29]),
        amount_cents=amount_cents,
        amount=round(amount_cents / 100.0, 2),
        individual_id_number=line[39:54].strip(),
        individual_name=line[54:76].strip(),
        addenda_indicator=line[78:79].strip(),   # NACHA pos 79 (0-based index 78)
        trace_number=line[79:94].strip(),          # NACHA pos 80-94 (15 chars)
        batch_number=batch_number,
        sec_code=sec_code,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_ccd_bytes(content: bytes) -> ParsedCCDFile:
    """Parse the raw bytes of a NACHA ACH CCD file.

    Args:
        content: Raw file bytes (ASCII-encoded fixed-width records).

    Returns:
        ParsedCCDFile with all batch and entry detail records.

    Raises:
        ValueError: If the file contains no file header record.
    """
    text = content.decode("ascii", errors="replace")
    # Strip trailing commas that appear when files are exported from Excel/CSV
    lines = [ln.rstrip(",") for ln in text.splitlines() if ln.strip()]

    file_header: FileHeaderRecord | None = None
    batches: list[ParsedBatch] = []
    current_header: BatchHeaderRecord | None = None
    current_entries: list[EntryDetailRecord] = []

    for raw_line in lines:
        line = _pad(raw_line)
        record_type = line[0]

        if record_type == "1":
            file_header = _parse_file_header(line)

        elif record_type == "5":
            # Flush any previously open batch (malformed file guard)
            if current_header is not None:
                batches.append(ParsedBatch(header=current_header, entries=current_entries))
                current_entries = []
            current_header = _parse_batch_header(line)

        elif record_type == "6":
            if current_header is not None:
                entry = _parse_entry_detail(
                    line,
                    batch_number=current_header.batch_number,
                    sec_code=current_header.sec_code,
                )
                current_entries.append(entry)

        elif record_type == "8":
            # Batch Control — close the current batch
            if current_header is not None:
                batches.append(ParsedBatch(header=current_header, entries=current_entries))
                current_header = None
                current_entries = []

        # Record types 7 (Addenda) and 9 (File Control) are skipped

    # Handle malformed file where batch control record is missing
    if current_header is not None and current_entries:
        batches.append(ParsedBatch(header=current_header, entries=current_entries))

    if file_header is None:
        raise ValueError(
            "Invalid CCD file: no file header record (type '1') found."
        )

    return ParsedCCDFile(
        file_header=file_header,
        batches=batches,
        entry_count=sum(len(b.entries) for b in batches),
    )
