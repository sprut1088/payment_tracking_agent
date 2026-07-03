"""Tests for the CCD parser (Prompt 09)."""

from __future__ import annotations

from pathlib import Path

from payment_tracking_agent.parsers.ccd import (
    ParsedCcdEntry,
    mask_account_number,
    parse_ccd_file,
)


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "demo-data"
    / "local-folder-demo"
    / "batch_1100"
    / "ccd"
    / "batch_1100.ach"
)


def test_mask_account_number_keeps_last_four() -> None:
    assert mask_account_number("70000000000000001") == "*************0001"
    assert mask_account_number("  12345678  ") == "****5678"
    assert mask_account_number("12") == "**"


def test_parse_ccd_file_returns_entry_details(tmp_path: Path) -> None:
    parsed = parse_ccd_file(FIXTURE)

    assert parsed.source_file == "batch_1100.ach"
    assert parsed.syntax_valid is True
    assert parsed.errors == []

    fixture_type_6_count = sum(
        1 for line in FIXTURE.read_text().splitlines() if line.startswith("6")
    )
    assert len(parsed.entries) == fixture_type_6_count

    first = parsed.entries[0]
    assert isinstance(first, ParsedCcdEntry)
    assert first.record_type_code == "6"
    assert first.transaction_code == "22"
    assert first.receiving_dfi_identification == "02100002"
    assert first.check_digit == "1"
    assert first.dfi_account_number == "70000000000000001"
    assert first.amount_cents == 18500
    assert first.individual_id_number == "CUST00000000001"
    assert first.individual_name == "ACME SUPPLY"
    assert first.trace_number == "123456780000001"


def test_every_type_6_line_is_94_chars() -> None:
    for line_no, raw in enumerate(FIXTURE.read_text().split("\n"), start=1):
        line = raw.rstrip("\r\n")
        if not line or not line.startswith("6"):
            continue
        assert len(line) == 94, (
            f"line {line_no}: expected 94 chars, got {len(line)}"
        )


def test_parsed_entries_have_nonempty_and_distinct_id_and_name() -> None:
    parsed = parse_ccd_file(FIXTURE)
    assert parsed.entries, "expected at least one type 6 entry"
    for entry in parsed.entries:
        assert entry.trace_number, "trace_number must be non-empty"
        assert entry.trace_number.isdigit(), (
            f"trace_number should be numeric, got {entry.trace_number!r}"
        )
        assert entry.individual_name, "individual_name must be non-empty"
        assert not entry.individual_name.isdigit(), (
            f"individual_name must not look like a numeric id, got {entry.individual_name!r}"
        )
        assert entry.individual_id_number, "individual_id_number must be non-empty"
        assert entry.individual_id_number != entry.individual_name


def test_parse_ccd_file_flags_short_line(tmp_path: Path) -> None:
    bad = tmp_path / "bad.ach"
    bad.write_text("6220210000217000000000000000010000018500SHORT LINE\n", encoding="utf-8")

    parsed = parse_ccd_file(bad)

    assert parsed.syntax_valid is False
    assert parsed.entries == []
    assert any("expected 94" in err for err in parsed.errors)


def test_parse_ccd_file_flags_non_numeric_amount(tmp_path: Path) -> None:
    line = (
        "6"
        + "22"
        + "02100002"
        + "1"
        + "70000000000000001"
        + "ABCDEFGHIJ"  # amount slot, non-numeric
        + "ACME SUPPLY    "
        + "NAME                  "
        + "  "
        + " "
        + "123456789001001"
    )
    assert len(line) == 94
    bad = tmp_path / "bad_amount.ach"
    bad.write_text(line + "\n", encoding="utf-8")

    parsed = parse_ccd_file(bad)

    assert parsed.syntax_valid is False
    assert parsed.entries == []
    assert any("not numeric" in err for err in parsed.errors)
