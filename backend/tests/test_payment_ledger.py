"""Tests for the payment ledger foundation (Prompt 09)."""

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
from payment_tracking_agent.simulator.folder_watcher import (
    FolderWatcher,
    get_folder_watcher,
)
from payment_tracking_agent.simulator.scenario_state import (
    ScenarioStateStore,
    get_scenario_state,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BATCH_1100_CCD = (
    REPO_ROOT
    / "demo-data"
    / "local-folder-demo"
    / "batch_1100"
    / "ccd"
    / "batch_1100.ach"
)


def _make_settings(root: Path) -> Settings:
    return Settings(
        demo_flow_root=root,
        settlement_delay_seconds=120,
        returns_delay_seconds=240,
        poll_interval_seconds=1,
    )


def _seed_batch_1100(watcher: FolderWatcher) -> Path:
    watcher.ensure_directories()
    dest = watcher.config_view.inbox_dir / BATCH_1100_CCD.name
    shutil.copyfile(BATCH_1100_CCD, dest)
    return dest


def _expected_entry_count() -> int:
    return sum(
        1 for line in BATCH_1100_CCD.read_text().splitlines() if line.startswith("6")
    )


def test_scan_ccd_creates_ledger_payments_sent_to_scheme(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    ledger = PaymentLedger()
    watcher = FolderWatcher(settings=settings, store=store, ledger=ledger)

    _seed_batch_1100(watcher)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)

    payments = ledger.list_payments()
    assert len(payments) == _expected_entry_count()

    for payment in payments:
        assert payment.current_status == PaymentStatus.SENT_TO_SCHEME
        assert payment.batch_key == "batch_1100"
        assert payment.source_file == "batch_1100.ach"
        assert payment.amount_cents > 0
        assert payment.masked_account_number.startswith("*")
        assert not any(c.isdigit() for c in payment.masked_account_number[:-4])
        assert payment.individual_name != ""
        assert not payment.individual_name.isdigit()
        assert payment.individual_id_number != ""
        assert payment.individual_id_number != payment.individual_name
        assert payment.trace_number, "trace_number must be non-empty"
        assert payment.trace_number.isdigit()
        assert len(payment.status_history) == 1
        assert payment.status_history[0].status == PaymentStatus.SENT_TO_SCHEME
        assert (
            payment.evidence[0].summary
            == "CCD file uploaded and bank-side syntax validation passed."
        )


def test_scan_ccd_is_idempotent_across_calls(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    ledger = PaymentLedger()
    watcher = FolderWatcher(settings=settings, store=store, ledger=ledger)

    _seed_batch_1100(watcher)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)

    watcher.scan_ccd(now=t0)
    watcher.scan_ccd(now=t0)

    assert len(ledger.list_payments()) == _expected_entry_count()


def test_ledger_reset_clears_payments(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    ledger = PaymentLedger()
    watcher = FolderWatcher(settings=settings, store=store, ledger=ledger)

    _seed_batch_1100(watcher)
    watcher.scan_ccd()
    assert ledger.list_payments()

    ledger.reset()
    assert ledger.list_payments() == []


@pytest.fixture
def api_client(tmp_path: Path):
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    ledger = PaymentLedger()
    watcher = FolderWatcher(settings=settings, store=store, ledger=ledger)
    app.dependency_overrides[get_folder_watcher] = lambda: watcher
    app.dependency_overrides[get_scenario_state] = lambda: store
    app.dependency_overrides[get_payment_ledger] = lambda: ledger
    try:
        yield TestClient(app), watcher, store, ledger
    finally:
        app.dependency_overrides.pop(get_folder_watcher, None)
        app.dependency_overrides.pop(get_scenario_state, None)
        app.dependency_overrides.pop(get_payment_ledger, None)


def test_api_get_payments_returns_ledger(api_client) -> None:
    client, watcher, _store, _ledger = api_client
    client.post("/api/demo-flow/ensure-folders")
    _seed_batch_1100(watcher)
    client.post("/api/demo-flow/scan-ccd")

    response = client.get("/api/demo-flow/payments")
    assert response.status_code == 200
    body = response.json()
    assert "as_of" in body
    assert len(body["payments"]) == _expected_entry_count()

    first = body["payments"][0]
    assert first["current_status"] == "SENT TO SCHEME"
    assert first["batch_key"] == "batch_1100"
    assert first["masked_account_number"].startswith("*")
    assert first["amount_cents"] > 0
    assert first["trace_number"] and first["trace_number"].isdigit()
    for payment in body["payments"]:
        assert payment["trace_number"], (
            f"payment {payment['payment_id']} should have a non-empty trace_number"
        )
    assert first["evidence"][0]["summary"] == (
        "CCD file uploaded and bank-side syntax validation passed."
    )


def test_api_reset_clears_ledger_and_state(api_client) -> None:
    client, watcher, store, ledger = api_client
    client.post("/api/demo-flow/ensure-folders")
    _seed_batch_1100(watcher)
    client.post("/api/demo-flow/scan-ccd")

    assert ledger.list_payments()
    assert store.list_batches()

    reset = client.post("/api/demo-flow/reset")
    assert reset.status_code == 204

    payments = client.get("/api/demo-flow/payments").json()
    assert payments["payments"] == []
    state = client.get("/api/demo-flow/state").json()
    assert state["batches"] == []
