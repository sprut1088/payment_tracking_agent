"""HTTP routes for the local-folder demo flow (Prompt 04).

Foundation endpoints only. No ACH parsing, no payment-level ledger updates —
those are added in later prompts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from payment_tracking_agent.models.demo_flow import (
    DemoFlowConfigView,
    DemoFlowState,
    ScanResult,
)
from payment_tracking_agent.simulator.folder_watcher import (
    FolderWatcher,
    get_folder_watcher,
)
from payment_tracking_agent.simulator.scenario_state import (
    ScenarioStateStore,
    get_scenario_state,
)

router = APIRouter(prefix="/api/demo-flow", tags=["demo-flow"])


@router.get("/config", response_model=DemoFlowConfigView)
def get_config(watcher: FolderWatcher = Depends(get_folder_watcher)) -> DemoFlowConfigView:
    return watcher.config_view


@router.post("/ensure-folders", response_model=DemoFlowConfigView)
def ensure_folders(
    watcher: FolderWatcher = Depends(get_folder_watcher),
) -> DemoFlowConfigView:
    watcher.ensure_directories()
    return watcher.config_view


@router.post("/scan-ccd", response_model=ScanResult)
def scan_ccd(watcher: FolderWatcher = Depends(get_folder_watcher)) -> ScanResult:
    return watcher.scan_ccd()


@router.post("/check-settlement", response_model=ScanResult)
def check_settlement(watcher: FolderWatcher = Depends(get_folder_watcher)) -> ScanResult:
    return watcher.check_settlement()


@router.post("/check-returns", response_model=ScanResult)
def check_returns(watcher: FolderWatcher = Depends(get_folder_watcher)) -> ScanResult:
    return watcher.check_returns()


@router.get("/state", response_model=DemoFlowState)
def get_state(store: ScenarioStateStore = Depends(get_scenario_state)) -> DemoFlowState:
    return DemoFlowState(
        as_of=datetime.now(timezone.utc),
        batches=store.list_batches(),
        detected_files=store.list_detected_files(),
    )


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset(store: ScenarioStateStore = Depends(get_scenario_state)) -> None:
    store.reset()
