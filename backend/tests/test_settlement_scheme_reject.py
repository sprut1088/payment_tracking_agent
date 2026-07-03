"""Tests for settlement + scheme-reject ledger updates (Prompt 10)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from payment_tracking_agent.config import Settings
from payment_tracking_agent.ledger.store import PaymentLedger, get_payment_ledger
from payment_tracking_agent.main import app
from payment_tracking_agent.models.ledger import PaymentStatus
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

REJECTED_TRACE = "123456780000004"


def _make_settings(root: Path) -> Settings:
    return Settings(
        demo_flow_root=root,
        settlement_delay_seconds=120,
        returns_delay_seconds=240,
        poll_interval_seconds=1,
    )


def _build_watcher(tmp_path: Path) -> tuple[FolderWatcher, PaymentLedger, ScenarioStateStore]:
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


def _reject_fixture_trace() -> str:
    payload = json.loads(BATCH_1100_REJECT.read_text(encoding="utf-8"))
    return payload["rejections"][0]["payment_trace_number"]


def test_reject_fixture_targets_a_real_ccd_trace() -> None:
    fixture_trace = _reject_fixture_trace()
    ccd_traces = {line[79:94].rstrip() for line in BATCH_1100_CCD.read_text().splitlines() if line.startswith("6")}
    assert fixture_trace in ccd_traces


def test_scan_ccd_marks_all_payments_sent_to_scheme(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)

    watcher.scan_ccd(now=t0)

    payments = ledger.list_payments()
    assert payments
    assert all(p.current_status == PaymentStatus.SENT_TO_SCHEME for p in payments)


def test_settlement_only_moves_payments_to_beneficiary_bank(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)

    _drop_settlement(watcher)
    watcher.check_settlement(now=t0)

    payments = ledger.list_payments()
    assert payments
    for payment in payments:
        assert payment.current_status == PaymentStatus.WITH_BENEFICIARY_BANK
        summaries = " ".join(e.summary for e in payment.evidence)
        assert "Settlement summary" in summaries
        assert "not payment-level clearing evidence" in summaries
        assert PaymentStatus.WITH_BENEFICIARY_BANK in {
            e.status for e in payment.status_history
        }
        assert len(payment.status_history) == 2


def test_scheme_reject_only_updates_matched_and_leaves_others(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)

    _drop_reject(watcher)
    watcher.check_settlement(now=t0)

    rejected = [p for p in ledger.list_payments() if p.trace_number == REJECTED_TRACE]
    others = [p for p in ledger.list_payments() if p.trace_number != REJECTED_TRACE]

    assert len(rejected) == 1
    assert rejected[0].current_status == PaymentStatus.REJECTED_BY_SCHEME
    assert others
    assert all(p.current_status == PaymentStatus.SENT_TO_SCHEME for p in others)

    reject_evidence_summaries = " ".join(e.summary for e in rejected[0].evidence)
    assert "Scheme reject file" in reject_evidence_summaries
    assert "SCHEME-VAL-001" in reject_evidence_summaries


def test_settlement_and_scheme_reject_together(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)

    _drop_settlement(watcher)
    _drop_reject(watcher)
    watcher.check_settlement(now=t0)

    payments = ledger.list_payments()
    rejected = [p for p in payments if p.trace_number == REJECTED_TRACE]
    others = [p for p in payments if p.trace_number != REJECTED_TRACE]

    assert len(rejected) == 1
    assert rejected[0].current_status == PaymentStatus.REJECTED_BY_SCHEME
    assert others
    assert all(p.current_status == PaymentStatus.WITH_BENEFICIARY_BANK for p in others)


def test_no_payment_is_ever_marked_cleared(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)
    _drop_settlement(watcher)
    _drop_reject(watcher)
    watcher.check_settlement(now=t0)

    for payment in ledger.list_payments():
        assert payment.current_status.value != "CLEARED"
        for event in payment.status_history:
            assert event.status.value != "CLEARED"


def test_repeat_check_settlement_does_not_double_append_evidence(tmp_path: Path) -> None:
    watcher, ledger, _store = _build_watcher(tmp_path)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)

    _drop_settlement(watcher)
    _drop_reject(watcher)
    watcher.check_settlement(now=t0)
    watcher.check_settlement(now=t0)

    for payment in ledger.list_payments():
        assert len(payment.status_history) == 2


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


def test_api_check_settlement_updates_payments(api_client) -> None:
    client, watcher, _ledger = api_client
    client.post("/api/demo-flow/ensure-folders")
    shutil.copyfile(BATCH_1100_CCD, watcher.config_view.inbox_dir / BATCH_1100_CCD.name)
    client.post("/api/demo-flow/scan-ccd")

    _drop_settlement(watcher)
    _drop_reject(watcher)
    response = client.post("/api/demo-flow/check-settlement")
    assert response.status_code == 200

    payments = client.get("/api/demo-flow/payments").json()["payments"]
    assert payments
    statuses = {p["trace_number"]: p["current_status"] for p in payments}
    assert statuses[REJECTED_TRACE] == "REJECTED BY SCHEME"
    other_statuses = {
        s for trace, s in statuses.items() if trace != REJECTED_TRACE
    }
    assert other_statuses == {"WITH BENEFICIARY BANK"}
    for payment in payments:
        assert payment["current_status"] != "CLEARED"
