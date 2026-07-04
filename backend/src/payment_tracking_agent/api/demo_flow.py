"""HTTP routes for the local-folder demo flow (Prompt 04).

Foundation endpoints only. No ACH parsing, no payment-level ledger updates —
those are added in later prompts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from payment_tracking_agent.agents.ai_explanation import (
    AIExplanationCallError,
    AIExplanationConfigError,
    AIExplanationService,
    get_ai_explanation_service,
)
from payment_tracking_agent.ledger.store import PaymentLedger, get_payment_ledger
from payment_tracking_agent.models.ai_explanation import AIExplanationResponse
from payment_tracking_agent.models.demo_flow import (
    DemoFlowConfigView,
    DemoFlowState,
    ScanResult,
)
from payment_tracking_agent.models.ledger import PaymentLedgerView
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


@router.get("/payments", response_model=PaymentLedgerView)
def get_payments(
    ledger: PaymentLedger = Depends(get_payment_ledger),
) -> PaymentLedgerView:
    return PaymentLedgerView(
        as_of=datetime.now(timezone.utc),
        payments=ledger.list_payments(),
    )


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset(
    store: ScenarioStateStore = Depends(get_scenario_state),
    ledger: PaymentLedger = Depends(get_payment_ledger),
) -> None:
    store.reset()
    ledger.reset()


@router.post(
    "/payments/{payment_id}/ai-explanation",
    response_model=AIExplanationResponse,
    responses={
        404: {"description": "Payment not found in the ledger."},
        502: {"description": "AI provider call failed."},
        503: {"description": "AI provider is not configured."},
    },
)
def generate_ai_explanation(
    payment_id: str,
    ledger: PaymentLedger = Depends(get_payment_ledger),
    ai_service: AIExplanationService = Depends(get_ai_explanation_service),
) -> AIExplanationResponse:
    """Return a Claude-generated explanation for the payment.

    The AI never determines or changes payment status. This endpoint is
    read-only against the ledger: the ledger snapshot is fed to Claude and
    the response is returned as-is to the caller.
    """
    payment = ledger.get_payment(payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment {payment_id} not found in the ledger.",
        )
    if not ai_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Claude AI explanation is not configured. "
                "Set ANTHROPIC_API_KEY and restart the backend."
            ),
        )
    try:
        return ai_service.explain(payment)
    except AIExplanationConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except AIExplanationCallError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Anthropic Claude call failed: {exc}",
        ) from exc
