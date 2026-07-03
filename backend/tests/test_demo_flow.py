"""Tests for the local-folder demo flow foundation (Prompt 04)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from payment_tracking_agent.config import Settings
from payment_tracking_agent.main import app
from payment_tracking_agent.models.demo_flow import (
    BatchIntakeStatus,
    FileKind,
    SettlementSchemeEvidenceStatus,
)
from payment_tracking_agent.simulator.folder_watcher import (
    FolderWatcher,
    get_folder_watcher,
)
from payment_tracking_agent.simulator.scenario_state import (
    ScenarioStateStore,
    get_scenario_state,
)


def _make_settings(root: Path) -> Settings:
    return Settings(
        demo_flow_root=root,
        settlement_delay_seconds=120,
        returns_delay_seconds=240,
        poll_interval_seconds=1,
    )


def _write(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_ensure_directories_creates_all_folders(tmp_path: Path) -> None:
    watcher = FolderWatcher(settings=_make_settings(tmp_path), store=ScenarioStateStore())

    watcher.ensure_directories()

    cfg = watcher.config_view
    assert cfg.inbox_dir.is_dir()
    assert cfg.settlement_dir.is_dir()
    assert cfg.scheme_reject_dir.is_dir()
    assert cfg.returns_dir.is_dir()
    assert cfg.processed_dir.is_dir()


def test_scan_ccd_registers_batch_with_schedule(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    watcher = FolderWatcher(settings=settings, store=store)
    watcher.ensure_directories()

    ccd = _write(watcher.config_view.inbox_dir / "BATCH_001.ccd")
    t0 = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)

    result = watcher.scan_ccd(now=t0)

    assert result.new_batches == ["BATCH_001"]
    assert [f.path for f in result.new_files] == [ccd]

    batch = store.get_batch("BATCH_001")
    assert batch is not None
    assert batch.status == BatchIntakeStatus.AWAITING_SETTLEMENT
    assert batch.settlement_scheme_status == SettlementSchemeEvidenceStatus.NONE_AVAILABLE
    assert batch.uploaded_at == t0
    assert batch.expected_settlement_scan_at == t0 + timedelta(seconds=120)
    assert batch.expected_returns_scan_at == t0 + timedelta(seconds=240)
    assert batch.ccd_file.kind == FileKind.CCD


def test_check_settlement_only_sets_evidence_status(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    watcher = FolderWatcher(settings=settings, store=store)
    watcher.ensure_directories()
    cfg = watcher.config_view

    _write(cfg.inbox_dir / "BATCH_010.ccd")
    t0 = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)

    _write(cfg.settlement_dir / "BATCH_010.settlement.txt")
    watcher.check_settlement(now=t0 + timedelta(seconds=125))

    batch = store.get_batch("BATCH_010")
    assert batch is not None
    assert batch.settlement_scheme_status == SettlementSchemeEvidenceStatus.SETTLEMENT_AVAILABLE
    assert [f.filename for f in batch.settlement_files] == ["BATCH_010.settlement.txt"]
    assert batch.scheme_reject_files == []


def test_check_scheme_reject_only_sets_evidence_status(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    watcher = FolderWatcher(settings=settings, store=store)
    watcher.ensure_directories()
    cfg = watcher.config_view

    _write(cfg.inbox_dir / "BATCH_011.ccd")
    t0 = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)

    _write(cfg.scheme_reject_dir / "BATCH_011.reject.txt")
    watcher.check_settlement(now=t0 + timedelta(seconds=125))

    batch = store.get_batch("BATCH_011")
    assert batch is not None
    assert batch.settlement_scheme_status == SettlementSchemeEvidenceStatus.SCHEME_REJECT_AVAILABLE
    assert batch.settlement_files == []
    assert [f.filename for f in batch.scheme_reject_files] == ["BATCH_011.reject.txt"]


def test_repeat_scan_ccd_does_not_duplicate(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    watcher = FolderWatcher(settings=settings, store=store)
    watcher.ensure_directories()
    _write(watcher.config_view.inbox_dir / "BATCH_001.ccd")

    watcher.scan_ccd()
    second = watcher.scan_ccd()

    assert second.new_files == []
    assert second.new_batches == []
    assert len(store.list_batches()) == 1


def test_check_settlement_attaches_and_advances(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    watcher = FolderWatcher(settings=settings, store=store)
    watcher.ensure_directories()
    cfg = watcher.config_view

    _write(cfg.inbox_dir / "BATCH_001.ccd")
    t0 = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)

    _write(cfg.settlement_dir / "BATCH_001.settlement.txt")
    _write(cfg.scheme_reject_dir / "BATCH_001.reject.txt")

    result = watcher.check_settlement(now=t0 + timedelta(seconds=125))

    assert "BATCH_001" in result.batches_advanced
    batch = store.get_batch("BATCH_001")
    assert batch is not None
    assert batch.status == BatchIntakeStatus.AWAITING_RETURNS
    assert batch.settlement_scheme_status == (
        SettlementSchemeEvidenceStatus.SETTLEMENT_AND_SCHEME_REJECT_AVAILABLE
    )
    assert [f.filename for f in batch.settlement_files] == ["BATCH_001.settlement.txt"]
    assert [f.filename for f in batch.scheme_reject_files] == ["BATCH_001.reject.txt"]


def test_check_returns_marks_return_evidence_received(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    watcher = FolderWatcher(settings=settings, store=store)
    watcher.ensure_directories()
    cfg = watcher.config_view

    _write(cfg.inbox_dir / "BATCH_001.ccd")
    t0 = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)

    _write(cfg.returns_dir / "BATCH_001.return.ach")
    result = watcher.check_returns(now=t0 + timedelta(seconds=245))

    assert "BATCH_001" in result.batches_advanced
    batch = store.get_batch("BATCH_001")
    assert batch is not None
    assert batch.status == BatchIntakeStatus.RETURN_EVIDENCE_RECEIVED
    assert [f.filename for f in batch.return_files] == ["BATCH_001.return.ach"]


def test_unmatched_file_is_recorded_but_unattached(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    watcher = FolderWatcher(settings=settings, store=store)
    watcher.ensure_directories()
    cfg = watcher.config_view

    orphan = _write(cfg.returns_dir / "UNKNOWN.return.ach")
    result = watcher.check_returns()

    assert [f.path for f in result.new_files] == [orphan]
    assert result.new_batches == []
    assert store.has_seen(orphan)
    detected_paths = [f.path for f in store.list_detected_files()]
    assert orphan in detected_paths


def test_evidence_advances_status_within_settlement_window(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    watcher = FolderWatcher(settings=settings, store=store)
    watcher.ensure_directories()
    cfg = watcher.config_view

    _write(cfg.inbox_dir / "BATCH_020.ccd")
    t0 = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)

    _write(cfg.settlement_dir / "BATCH_020.settlement.txt")
    # Well before the expected_settlement_scan_at (t0 + 120s).
    result = watcher.check_settlement(now=t0 + timedelta(seconds=5))

    assert "BATCH_020" in result.batches_advanced
    batch = store.get_batch("BATCH_020")
    assert batch is not None
    assert batch.status == BatchIntakeStatus.AWAITING_RETURNS


@pytest.fixture
def api_client(tmp_path: Path):
    settings = _make_settings(tmp_path)
    store = ScenarioStateStore()
    watcher = FolderWatcher(settings=settings, store=store)
    app.dependency_overrides[get_folder_watcher] = lambda: watcher
    app.dependency_overrides[get_scenario_state] = lambda: store
    try:
        yield TestClient(app), watcher, store
    finally:
        app.dependency_overrides.pop(get_folder_watcher, None)
        app.dependency_overrides.pop(get_scenario_state, None)


def test_api_config_exposes_configured_paths(api_client) -> None:
    client, watcher, _ = api_client
    response = client.get("/api/demo-flow/config")
    assert response.status_code == 200
    body = response.json()
    assert body["settlement_delay_seconds"] == 120
    assert body["returns_delay_seconds"] == 240
    assert Path(body["inbox_dir"]) == watcher.config_view.inbox_dir
    assert Path(body["processed_dir"]) == watcher.config_view.processed_dir


def test_api_ensure_folders_creates_directories(api_client) -> None:
    client, watcher, _ = api_client
    response = client.post("/api/demo-flow/ensure-folders")
    assert response.status_code == 200
    body = response.json()
    cfg = watcher.config_view
    assert cfg.inbox_dir.is_dir()
    assert cfg.settlement_dir.is_dir()
    assert cfg.scheme_reject_dir.is_dir()
    assert cfg.returns_dir.is_dir()
    assert cfg.processed_dir.is_dir()
    assert Path(body["processed_dir"]) == cfg.processed_dir


def test_api_scan_ccd_registers_batch(api_client) -> None:
    client, watcher, store = api_client
    client.post("/api/demo-flow/ensure-folders")
    _write(watcher.config_view.inbox_dir / "BATCH_042.ccd")

    response = client.post("/api/demo-flow/scan-ccd")
    assert response.status_code == 200
    assert response.json()["new_batches"] == ["BATCH_042"]
    assert [b.batch_id for b in store.list_batches()] == ["BATCH_042"]


def test_api_check_settlement_attaches_files(api_client) -> None:
    client, watcher, store = api_client
    client.post("/api/demo-flow/ensure-folders")
    _write(watcher.config_view.inbox_dir / "BATCH_042.ccd")
    client.post("/api/demo-flow/scan-ccd")

    _write(watcher.config_view.settlement_dir / "BATCH_042.settlement.txt")
    _write(watcher.config_view.scheme_reject_dir / "BATCH_042.reject.txt")

    response = client.post("/api/demo-flow/check-settlement")
    assert response.status_code == 200
    body = response.json()
    filenames = [f["filename"] for f in body["new_files"]]
    assert "BATCH_042.settlement.txt" in filenames
    assert "BATCH_042.reject.txt" in filenames

    batch = store.get_batch("BATCH_042")
    assert batch is not None
    assert len(batch.settlement_files) == 1
    assert len(batch.scheme_reject_files) == 1
    assert batch.settlement_scheme_status == (
        SettlementSchemeEvidenceStatus.SETTLEMENT_AND_SCHEME_REJECT_AVAILABLE
    )


def test_api_check_returns_attaches_files(api_client) -> None:
    client, watcher, store = api_client
    client.post("/api/demo-flow/ensure-folders")
    _write(watcher.config_view.inbox_dir / "BATCH_042.ccd")
    client.post("/api/demo-flow/scan-ccd")

    _write(watcher.config_view.returns_dir / "BATCH_042.return.ach")

    response = client.post("/api/demo-flow/check-returns")
    assert response.status_code == 200
    body = response.json()
    assert [f["filename"] for f in body["new_files"]] == ["BATCH_042.return.ach"]

    batch = store.get_batch("BATCH_042")
    assert batch is not None
    assert len(batch.return_files) == 1


def test_api_state_returns_batches_and_detected_files(api_client) -> None:
    client, watcher, _ = api_client
    client.post("/api/demo-flow/ensure-folders")
    _write(watcher.config_view.inbox_dir / "BATCH_001.ccd")
    _write(watcher.config_view.returns_dir / "ORPHAN.return.ach")
    client.post("/api/demo-flow/scan-ccd")
    client.post("/api/demo-flow/check-returns")

    response = client.get("/api/demo-flow/state")
    assert response.status_code == 200
    body = response.json()
    assert [b["batch_id"] for b in body["batches"]] == ["BATCH_001"]
    assert body["batches"][0]["settlement_scheme_status"] == "NONE_AVAILABLE"
    filenames = sorted(f["filename"] for f in body["detected_files"])
    assert filenames == ["BATCH_001.ccd", "ORPHAN.return.ach"]
    assert "as_of" in body
