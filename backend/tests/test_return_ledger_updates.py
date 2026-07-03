"""Tests for NACHA return ledger updates (Prompt 11)."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from payment_tracking_agent.config import Settings
from payment_tracking_agent.ledger.store import PaymentLedger, get_payment_ledger
from payment_tracking_agent.main import app
from payment_tracking_agent.models.ledger import PaymentStatus
from payment_tracking_agent.parsers.nacha_return import parse_return_file
from payment_tracking_agent.simulator.folder_watcher import (
    FolderWatcher,
    get_folder_watcher,
)
from payment_tracking_agent.simulator.scenario_state import (
    ScenarioStateStore,
    get_scenario_state,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BATCH_1100_ROOT = REPO_ROOT / "demo-data" / "local-folder-demo" / "batch_1100"
BATCH_1100_CCD = BATCH_1100_ROOT / "ccd" / "batch_1100.ach"
BATCH_1100_SETTLEMENT = BATCH_1100_ROOT / "settlement" / "batch_1100_settlement.dat"
BATCH_1100_REJECT = BATCH_1100_ROOT / "scheme-reject" / "batch_1100_reject.json"
BATCH_1100_RETURN = BATCH_1100_ROOT / "returns" / "batch_1100_return.ach"

RETURNED_TRACE = "123456780000002"
REJECTED_TRACE = "123456780000004"


def _make_settings(root: Path) -> Settings:
    return Settings(
        demo_flow_root=root,
        settlement_delay_seconds=120,
        returns_delay_seconds=240,
        poll_interval_seconds=1,
    )


def _build_watcher(tmp_path: Path):
    store = ScenarioStateStore()
    ledger = PaymentLedger()
    watcher = FolderWatcher(settings=_make_settings(tmp_path), store=store, ledger=ledger)
    watcher.ensure_directories()
    shutil.copyfile(BATCH_1100_CCD, watcher.config_view.inbox_dir / BATCH_1100_CCD.name)
    return watcher, ledger, store


def _drop_settlement(watcher: FolderWatcher) -> None:
    shutil.copyfile(
        BATCH_1100_SETTLEMENT,
        watcher.config_view.settlement_dir / BATCH_1100_SETTLEMENT.name,
    )


def _drop_reject(watcher: FolderWatcher) -> None:
    shutil.copyfile(
        BATCH_1100_REJECT,
        watcher.config_view.scheme_reject_dir / BATCH_1100_REJECT.name,
    )


def _drop_return(watcher: FolderWatcher) -> None:
    shutil.copyfile(
        BATCH_1100_RETURN,
        watcher.config_view.returns_dir / BATCH_1100_RETURN.name,
    )


def test_return_fixture_targets_a_real_ccd_trace_and_avoids_rejected_trace() -> None:
    parsed = parse_return_file(BATCH_1100_RETURN)
    assert parsed.addenda, "expected at least one type 7 addenda 99 record"
    traces = {a.original_trace_number for a in parsed.addenda}
    assert RETURNED_TRACE in traces
    assert REJECTED_TRACE not in traces


def test_parse_return_file_extracts_reason_and_original_trace() -> None:
    parsed = parse_return_file(BATCH_1100_RETURN)
    addenda = parsed.addenda[0]
    assert addenda.record_type_code == "7"
    assert addenda.addenda_type_code == "99"
    assert addenda.return_reason_code == "R01"
    assert addenda.original_trace_number == RETURNED_TRACE
    assert addenda.trace_number and addenda.trace_number.isdigit()


def test_check_returns_moves_matched_trace_to_rejected_by_beneficiary_bank(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)

    _drop_settlement(watcher)
    _drop_reject(watcher)
    watcher.check_settlement(now=t0)

    _drop_return(watcher)
    watcher.check_returns(now=t0)

    payments = ledger.list_payments()
    by_trace = {p.trace_number: p for p in payments}

    assert by_trace[RETURNED_TRACE].current_status == PaymentStatus.REJECTED_BY_BENEFICIARY_BANK
    assert by_trace[REJECTED_TRACE].current_status == PaymentStatus.REJECTED_BY_SCHEME

    others = [
        p for p in payments if p.trace_number not in {RETURNED_TRACE, REJECTED_TRACE}
    ]
    assert others
    assert all(p.current_status == PaymentStatus.WITH_BENEFICIARY_BANK for p in others)


def test_return_evidence_is_appended_to_history(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)
    _drop_settlement(watcher)
    watcher.check_settlement(now=t0)
    _drop_return(watcher)
    watcher.check_returns(now=t0)

    returned = next(p for p in ledger.list_payments() if p.trace_number == RETURNED_TRACE)
    statuses = [event.status for event in returned.status_history]
    assert statuses == [
        PaymentStatus.SENT_TO_SCHEME,
        PaymentStatus.WITH_BENEFICIARY_BANK,
        PaymentStatus.REJECTED_BY_BENEFICIARY_BANK,
    ]
    summary_text = " ".join(e.summary for e in returned.evidence)
    assert BATCH_1100_RETURN.name in summary_text
    assert RETURNED_TRACE in summary_text
    assert "R01" in summary_text
    assert "beneficiary bank" in summary_text.lower()


def test_return_does_not_overwrite_scheme_rejected_payment(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)
    _drop_reject(watcher)
    watcher.check_settlement(now=t0)

    # Craft a spurious return file whose addenda targets the scheme-rejected trace.
    spurious = watcher.config_view.returns_dir / "batch_1100_spurious_return.ach"
    addenda = (
        "7"
        + "99"
        + "R01"
        + REJECTED_TRACE
        + "260703"
        + "02100002"
        + " " * 44
        + "987654320000099"
    )
    assert len(addenda) == 94
    spurious.write_text(addenda + "\n", encoding="utf-8")

    watcher.check_returns(now=t0)

    rejected = next(p for p in ledger.list_payments() if p.trace_number == REJECTED_TRACE)
    assert rejected.current_status == PaymentStatus.REJECTED_BY_SCHEME


def test_repeat_check_returns_is_idempotent(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)
    _drop_settlement(watcher)
    watcher.check_settlement(now=t0)
    _drop_return(watcher)

    watcher.check_returns(now=t0)
    watcher.check_returns(now=t0)

    returned = next(p for p in ledger.list_payments() if p.trace_number == RETURNED_TRACE)
    assert returned.current_status == PaymentStatus.REJECTED_BY_BENEFICIARY_BANK
    assert len(returned.status_history) == 3


def test_unmatched_return_trace_does_not_modify_payments(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)

    spurious = watcher.config_view.returns_dir / "batch_1100_unmatched.ach"
    addenda = (
        "7"
        + "99"
        + "R02"
        + "999999999999999"
        + "260703"
        + "02100002"
        + " " * 44
        + "987654320000998"
    )
    assert len(addenda) == 94
    spurious.write_text(addenda + "\n", encoding="utf-8")

    watcher.check_returns(now=t0)

    payments = ledger.list_payments()
    assert payments
    assert all(p.current_status == PaymentStatus.SENT_TO_SCHEME for p in payments)


def test_no_payment_is_marked_cleared_after_full_flow(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)
    _drop_settlement(watcher)
    _drop_reject(watcher)
    watcher.check_settlement(now=t0)
    _drop_return(watcher)
    watcher.check_returns(now=t0)

    for payment in ledger.list_payments():
        assert payment.current_status.value != "CLEARED"
        for event in payment.status_history:
            assert event.status.value != "CLEARED"


def test_full_flow_produces_expected_status_counts(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)
    _drop_settlement(watcher)
    _drop_reject(watcher)
    watcher.check_settlement(now=t0)
    _drop_return(watcher)
    watcher.check_returns(now=t0)

    counts: dict[PaymentStatus, int] = {}
    for payment in ledger.list_payments():
        counts[payment.current_status] = counts.get(payment.current_status, 0) + 1

    assert counts.get(PaymentStatus.WITH_BENEFICIARY_BANK, 0) == 14
    assert counts.get(PaymentStatus.REJECTED_BY_SCHEME, 0) == 1
    assert counts.get(PaymentStatus.REJECTED_BY_BENEFICIARY_BANK, 0) == 1
    assert PaymentStatus.SENT_TO_SCHEME not in counts
    assert PaymentStatus.WITH_BANK not in counts


@pytest.fixture
def api_client(tmp_path: Path):
    store = ScenarioStateStore()
    ledger = PaymentLedger()
    watcher = FolderWatcher(settings=_make_settings(tmp_path), store=store, ledger=ledger)
    app.dependency_overrides[get_folder_watcher] = lambda: watcher
    app.dependency_overrides[get_scenario_state] = lambda: store
    app.dependency_overrides[get_payment_ledger] = lambda: ledger
    try:
        yield TestClient(app), watcher, ledger
    finally:
        app.dependency_overrides.pop(get_folder_watcher, None)
        app.dependency_overrides.pop(get_scenario_state, None)
        app.dependency_overrides.pop(get_payment_ledger, None)


def test_api_check_returns_updates_ledger(api_client) -> None:
    client, watcher, _ledger = api_client
    client.post("/api/demo-flow/ensure-folders")
    shutil.copyfile(BATCH_1100_CCD, watcher.config_view.inbox_dir / BATCH_1100_CCD.name)
    client.post("/api/demo-flow/scan-ccd")

    _drop_settlement(watcher)
    _drop_reject(watcher)
    client.post("/api/demo-flow/check-settlement")

    _drop_return(watcher)
    response = client.post("/api/demo-flow/check-returns")
    assert response.status_code == 200

    payments = client.get("/api/demo-flow/payments").json()["payments"]
    statuses = {p["trace_number"]: p["current_status"] for p in payments}
    assert statuses[RETURNED_TRACE] == "REJECTED BY BENEFICIARY BANK"
    assert statuses[REJECTED_TRACE] == "REJECTED BY SCHEME"
    other_statuses = {
        s
        for trace, s in statuses.items()
        if trace not in {RETURNED_TRACE, REJECTED_TRACE}
    }
    assert other_statuses == {"WITH BENEFICIARY BANK"}
    for payment in payments:
        assert payment["current_status"] != "CLEARED"
