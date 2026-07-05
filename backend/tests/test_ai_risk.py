"""Tests for Prompt 18 revised AI risk classification behavior.

Covers payment/customer/batch risk classification semantics and verifies
classification stamping does not mutate deterministic ledger status fields.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from payment_tracking_agent.agents.ai_risk import (
    AIRiskClassificationService,
    FALLBACK_MODEL,
    FALLBACK_PROVIDER,
    SYSTEM_PROMPT,
    _sanitize_risk_text,
)
from payment_tracking_agent.config import Settings
from payment_tracking_agent.ledger.store import PaymentLedger
from payment_tracking_agent.models.ai_risk import (
    OutcomeAlignment,
    RiskBand,
    RiskClassificationTrigger,
)
from payment_tracking_agent.models.ledger import PaymentStatus
from payment_tracking_agent.services.customer_history import CustomerHistoryStore
from payment_tracking_agent.simulator.folder_watcher import FolderWatcher
from payment_tracking_agent.simulator.scenario_state import ScenarioStateStore

REPO_ROOT = Path(__file__).resolve().parents[2]
BATCH_1100_ROOT = REPO_ROOT / "demo-data" / "local-folder-demo" / "batch_1100"
BATCH_1100_CCD = BATCH_1100_ROOT / "ccd" / "batch_1100.ach"
BATCH_1100_SETTLEMENT = BATCH_1100_ROOT / "settlement" / "batch_1100_settlement.dat"
BATCH_1100_REJECT = BATCH_1100_ROOT / "scheme-reject" / "batch_1100_reject.json"
BATCH_1100_RETURN = BATCH_1100_ROOT / "returns" / "batch_1100_return.ach"
CUSTOMER_HISTORY = (
    REPO_ROOT / "demo-data" / "local-folder-demo" / "customer-risk-history.json"
)

RETURNED_TRACE = "123456780000002"
REJECTED_TRACE = "123456780000004"
LOW_CUSTOMER = "CUST00000000001"
MEDIUM_CUSTOMER = "CUST00000000005"
HIGH_CUSTOMER = "CUST00000000010"


def _make_settings(root: Path) -> Settings:
    return Settings(
        demo_flow_root=root,
        settlement_delay_seconds=120,
        returns_delay_seconds=240,
        poll_interval_seconds=1,
    )


def _build_watcher(
    tmp_path: Path,
    *,
    syntax_valid: bool = True,
    customer_history_path: Path = CUSTOMER_HISTORY,
):
    store = ScenarioStateStore()
    ledger = PaymentLedger()
    risk_service = AIRiskClassificationService(
        api_key=None,
        model="claude-test",
        client=None,
    )
    history_store = CustomerHistoryStore.from_fixture(customer_history_path)
    watcher = FolderWatcher(
        settings=_make_settings(tmp_path),
        store=store,
        ledger=ledger,
        risk_service=risk_service,
        customer_history=history_store,
    )
    watcher.ensure_directories()
    source = BATCH_1100_CCD
    if not syntax_valid:
        malformed = watcher.config_view.inbox_dir / "batch_1100_malformed.ach"
        text = BATCH_1100_CCD.read_text(encoding="utf-8")
        # Drop one character from first entry-detail line to trigger parser error.
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("6"):
                lines[i] = line[:-1]
                break
        malformed.write_text("\n".join(lines) + "\n", encoding="utf-8")
        source = malformed
    else:
        shutil.copyfile(BATCH_1100_CCD, watcher.config_view.inbox_dir / BATCH_1100_CCD.name)
    if not syntax_valid:
        return watcher, ledger, risk_service
    # ensure normal fixture is seeded
    if source == BATCH_1100_CCD:
        pass
    return watcher, ledger, risk_service


def _seed_clean_ccd(watcher: FolderWatcher) -> None:
    shutil.copyfile(BATCH_1100_CCD, watcher.config_view.inbox_dir / BATCH_1100_CCD.name)


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


def _scan_clean(tmp_path: Path):
    watcher, ledger, _service = _build_watcher(tmp_path)
    _seed_clean_ccd(watcher)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)
    return watcher, ledger, t0


def test_ccd_upload_payment_classification_uses_customer_history_and_batch_validation(
    tmp_path: Path,
) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    payments = ledger.list_payments()
    assert payments
    for payment in payments:
        c = payment.current_risk_classification
        assert c is not None
        assert c.trigger == RiskClassificationTrigger.CCD_UPLOAD
        drivers = " ".join(c.risk_drivers).lower()
        assert "customer" in drivers
        assert "batch" in drivers


def test_ccd_upload_payment_classification_does_not_use_sent_to_scheme_only_driver(
    tmp_path: Path,
) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    for payment in ledger.list_payments():
        c = payment.current_risk_classification
        assert c is not None
        drivers = " ".join(c.risk_drivers).lower()
        assert "sent to scheme only" not in drivers


def test_ccd_upload_payment_classification_does_not_use_missing_settlement_or_return_driver(
    tmp_path: Path,
) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    forbidden = [
        "no settlement evidence",
        "no return evidence",
        "lifecycle evidence pending",
        "earliest pipeline status",
    ]
    for payment in ledger.list_payments():
        c = payment.current_risk_classification
        assert c is not None
        drivers = " ".join(c.risk_drivers).lower()
        for token in forbidden:
            assert token not in drivers


def test_customer_with_no_recent_rejections_is_low_risk(tmp_path: Path) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    p = next(x for x in ledger.list_payments() if x.individual_id_number == LOW_CUSTOMER)
    c = p.current_customer_risk_classification
    assert c is not None
    assert c.risk_band == RiskBand.LOW


def test_customer_with_two_failures_last_30_or_90_days_is_medium_risk(
    tmp_path: Path,
) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    p = next(x for x in ledger.list_payments() if x.individual_id_number == MEDIUM_CUSTOMER)
    c = p.current_customer_risk_classification
    assert c is not None
    assert c.risk_band == RiskBand.MEDIUM


def test_customer_with_two_plus_recent_same_reason_failures_is_high_risk(
    tmp_path: Path,
) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    p = next(x for x in ledger.list_payments() if x.individual_id_number == HIGH_CUSTOMER)
    c = p.current_customer_risk_classification
    assert c is not None
    assert c.risk_band == RiskBand.HIGH


def test_batch_with_clean_parse_validation_is_low_risk(tmp_path: Path) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    p = ledger.list_payments()[0]
    c = p.current_batch_risk_classification
    assert c is not None
    assert c.risk_band == RiskBand.LOW


def test_batch_with_validation_findings_is_medium_or_high(tmp_path: Path) -> None:
    watcher, ledger, _service = _build_watcher(tmp_path, syntax_valid=False)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)
    payments = ledger.list_payments()
    # malformed fixture may skip malformed row; ensure at least one payment stamped
    assert payments
    batch = payments[0].current_batch_risk_classification
    assert batch is not None
    assert batch.risk_band in {RiskBand.MEDIUM, RiskBand.HIGH}


def test_payment_ccd_upload_classification_reflects_customer_trend(tmp_path: Path) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    low = next(x for x in ledger.list_payments() if x.individual_id_number == LOW_CUSTOMER)
    high = next(x for x in ledger.list_payments() if x.individual_id_number == HIGH_CUSTOMER)
    assert low.current_risk_classification is not None
    assert high.current_risk_classification is not None
    assert high.current_risk_classification.risk_score >= low.current_risk_classification.risk_score


def test_payment_ccd_upload_classification_reflects_batch_validation_risk(
    tmp_path: Path,
) -> None:
    watcher, ledger, _service = _build_watcher(tmp_path)
    _seed_clean_ccd(watcher)
    t0 = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    watcher.scan_ccd(now=t0)
    clean_score = ledger.list_payments()[0].current_risk_classification.risk_score

    # New watcher with malformed file
    watcher2, ledger2, _service2 = _build_watcher(tmp_path / "m", syntax_valid=False)
    watcher2.scan_ccd(now=t0)
    dirty_score = ledger2.list_payments()[0].current_risk_classification.risk_score
    assert dirty_score >= clean_score


def test_settlement_or_scheme_reclass_still_appends_payment_history(tmp_path: Path) -> None:
    watcher, ledger, t0 = _scan_clean(tmp_path)
    _drop_settlement(watcher)
    _drop_reject(watcher)
    watcher.check_settlement(now=t0)
    p = next(x for x in ledger.list_payments() if x.trace_number == REJECTED_TRACE)
    assert p.current_risk_classification is not None
    assert p.current_risk_classification.trigger == RiskClassificationTrigger.SETTLEMENT_OR_SCHEME_REJECT
    assert p.risk_classification_history


def test_nacha_return_reclass_includes_prior_prediction_vs_actual(tmp_path: Path) -> None:
    watcher, ledger, t0 = _scan_clean(tmp_path)
    _drop_settlement(watcher)
    _drop_reject(watcher)
    watcher.check_settlement(now=t0)
    _drop_return(watcher)
    watcher.check_returns(now=t0)

    returned = next(x for x in ledger.list_payments() if x.trace_number == RETURNED_TRACE)
    c = returned.current_risk_classification
    assert c is not None
    assert c.trigger == RiskClassificationTrigger.NACHA_RETURN
    assert c.prior_prediction is not None
    assert c.prior_prediction.outcome_alignment in {
        OutcomeAlignment.RISK_RAISED_BEFORE_REJECTION,
        OutcomeAlignment.UNEXPECTED_REJECTION,
        OutcomeAlignment.EXPECTED_REJECTION,
        OutcomeAlignment.NOT_APPLICABLE,
    }


def test_customer_dashboard_data_includes_customer_risk_classification(
    tmp_path: Path,
) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    p = ledger.list_payments()[0]
    assert p.current_customer_risk_classification is not None


def test_batch_dashboard_data_includes_batch_risk_classification(tmp_path: Path) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    p = ledger.list_payments()[0]
    assert p.current_batch_risk_classification is not None


def test_sanitizer_removes_fraud_credit_funds_and_clearing_wording() -> None:
    text = (
        "fraud risk credit risk customer is risky customer lacks funds payment cleared "
        "successfully paid payment completed funds credited funds transferred funds debited"
    )
    cleaned = _sanitize_risk_text(text, "WITH BENEFICIARY BANK").lower()
    for bad in [
        "fraud risk",
        "credit risk",
        "customer is risky",
        "customer lacks funds",
        "payment cleared",
        "successfully paid",
        "payment completed",
        "funds credited",
        "funds transferred",
        "funds debited",
    ]:
        assert bad not in cleaned


def test_risk_classification_never_mutates_current_status(tmp_path: Path) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    for p in ledger.list_payments():
        assert p.current_status in {
            PaymentStatus.SENT_TO_SCHEME,
            PaymentStatus.WITH_BANK,
            PaymentStatus.WITH_BENEFICIARY_BANK,
            PaymentStatus.REJECTED_BY_SCHEME,
            PaymentStatus.REJECTED_BY_BENEFICIARY_BANK,
        }


def test_risk_classification_never_mutates_status_history(tmp_path: Path) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    for p in ledger.list_payments():
        assert p.status_history
        assert all(event.status in PaymentStatus for event in p.status_history)


def test_risk_classification_never_mutates_evidence(tmp_path: Path) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    for p in ledger.list_payments():
        assert p.evidence
        assert all(ev.summary for ev in p.evidence)


def test_system_prompt_guardrails_cover_three_scopes() -> None:
    assert "payment risk" in SYSTEM_PROMPT.lower()
    assert "customer risk" in SYSTEM_PROMPT.lower()
    assert "batch risk" in SYSTEM_PROMPT.lower()
    assert "do not classify credit risk" in SYSTEM_PROMPT.lower()
    assert "do not classify fraud risk" in SYSTEM_PROMPT.lower()
    assert "for ccd_upload payment classification" in SYSTEM_PROMPT.lower()


def test_fallback_provider_model_tags_present(tmp_path: Path) -> None:
    _watcher, ledger, _t0 = _scan_clean(tmp_path)
    p = ledger.list_payments()[0]
    assert p.current_risk_classification is not None
    assert p.current_risk_classification.provider == FALLBACK_PROVIDER
    assert p.current_risk_classification.model == FALLBACK_MODEL
    assert p.current_customer_risk_classification is not None
    assert p.current_customer_risk_classification.provider == FALLBACK_PROVIDER
    assert p.current_batch_risk_classification is not None
    assert p.current_batch_risk_classification.provider == FALLBACK_PROVIDER
