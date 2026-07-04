"""Tests for the Anthropic Claude AI explanation service (Prompt 16).

Tests must NEVER make real network calls. We inject a fake Anthropic
client via ``AIExplanationService(client=..., api_key=..., model=...)`` and
via FastAPI dependency overrides.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from payment_tracking_agent.agents.ai_explanation import (
    SYSTEM_PROMPT,
    AIExplanationCallError,
    AIExplanationConfigError,
    AIExplanationService,
    _reset_system_certs_injected_for_tests,
    _sanitize_ai_text,
    get_ai_explanation_service,
)
from payment_tracking_agent.ledger.store import PaymentLedger, get_payment_ledger
from payment_tracking_agent.main import app
from payment_tracking_agent.models.ai_explanation import AIExplanationResponse
from payment_tracking_agent.models.ledger import (
    Payment,
    PaymentEvidence,
    PaymentStatus,
    PaymentStatusEvent,
)


# ---------------------------------------------------------------------------
# Fake Anthropic SDK stand-ins
# ---------------------------------------------------------------------------


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, response_text: str, capture: dict[str, Any]) -> None:
        self._response_text = response_text
        self._capture = capture
        self.call_count = 0

    def create(self, **kwargs: Any) -> _FakeMessage:
        self.call_count += 1
        self._capture.update(kwargs)
        return _FakeMessage(self._response_text)


class FakeAnthropicClient:
    """Stand-in for ``anthropic.Anthropic`` with a captured ``messages.create``."""

    def __init__(self, response_text: str) -> None:
        self.capture: dict[str, Any] = {}
        self.messages = _FakeMessages(response_text, self.capture)


class RaisingAnthropicClient:
    """Client whose ``messages.create`` raises to exercise the 502 branch."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

        class _Raise:
            def create(_self, **_kwargs: Any) -> Any:
                raise self._exc

        self.messages = _Raise()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


CANNED_JSON = (
    '{"summary":"Payment moved to beneficiary bank after settlement summary.",'
    '"status_explanation":"Settlement summary is summary-level only; no '
    'payment-level clearing is claimed.",'
    '"evidence_used":["CCD batch upload","Settlement summary"],'
    '"limitations":["No return evidence received yet."],'
    '"recommended_action":"Monitor for NACHA returns in later cycles.",'
    '"customer_safe_message":"Your payment has been sent to the beneficiary bank."}'
)


def _make_payment(payment_id: str = "batch_1100:001") -> Payment:
    now = datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc)
    evidence = PaymentEvidence(
        source="ccd:batch_1100.ach",
        summary="CCD file uploaded and syntax validation passed.",
        recorded_at=now,
    )
    history = [
        PaymentStatusEvent(status=PaymentStatus.SENT_TO_SCHEME, at=now, evidence=evidence)
    ]
    return Payment(
        payment_id=payment_id,
        batch_key="batch_1100",
        source_file="batch_1100.ach",
        trace_number="123456780000001",
        transaction_code="22",
        receiving_dfi_identification="12345678",
        masked_account_number="****1234",
        amount_cents=10000,
        individual_id_number="CUST001",
        individual_name="TEST PAYER",
        current_status=PaymentStatus.WITH_BENEFICIARY_BANK,
        status_history=list(history),
        evidence=[evidence],
    )


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    ledger = get_payment_ledger()
    ledger.reset()
    yield
    app.dependency_overrides.pop(get_ai_explanation_service, None)
    ledger.reset()


# ---------------------------------------------------------------------------
# Unit tests for the service
# ---------------------------------------------------------------------------


def test_system_prompt_contains_required_guardrails() -> None:
    assert "Settlement summary is summary-level evidence only." in SYSTEM_PROMPT
    assert "WITH BENEFICIARY BANK" in SYSTEM_PROMPT
    assert "REJECTED BY SCHEME" in SYSTEM_PROMPT
    assert "REJECTED BY BENEFICIARY BANK" in SYSTEM_PROMPT
    assert "You must not invent payment status." in SYSTEM_PROMPT
    # Prompt 16 correction: explicit forbidden-wording rules.
    assert "Forbidden wording rules" in SYSTEM_PROMPT
    assert "'cleared'" in SYSTEM_PROMPT
    assert "bank-side syntax validation passed" in SYSTEM_PROMPT
    assert "'clearing'" in SYSTEM_PROMPT
    assert "debited" in SYSTEM_PROMPT and "transferred" in SYSTEM_PROMPT


def test_is_configured_false_without_api_key_or_client() -> None:
    service = AIExplanationService(api_key=None, model="claude-test")
    assert service.is_configured() is False


def test_is_configured_true_with_injected_client() -> None:
    service = AIExplanationService(
        api_key=None,
        model="claude-test",
        client=FakeAnthropicClient("{}"),
    )
    assert service.is_configured() is True


def test_explain_returns_typed_response_and_captures_prompt() -> None:
    payment = _make_payment()
    fake_client = FakeAnthropicClient(CANNED_JSON)
    service = AIExplanationService(
        api_key="unused-in-test",
        model="claude-test",
        client=fake_client,
    )

    result = service.explain(payment)

    assert isinstance(result, AIExplanationResponse)
    assert result.payment_id == payment.payment_id
    assert result.provider == "anthropic"
    assert result.model == "claude-test"
    assert result.summary.startswith("Payment moved to beneficiary bank")
    assert "CCD batch upload" in result.evidence_used
    assert "No return evidence received yet." in result.limitations
    assert result.recommended_action.startswith("Monitor")
    assert result.customer_safe_message

    # Prompt-level guardrails were passed to the client.
    assert fake_client.messages.call_count == 1
    assert fake_client.capture["model"] == "claude-test"
    assert "Settlement summary is summary-level evidence only." in fake_client.capture["system"]
    user_msg = fake_client.capture["messages"][0]["content"]
    assert payment.payment_id in user_msg
    assert payment.trace_number in user_msg
    assert "WITH BENEFICIARY BANK" in user_msg


def test_explain_raises_config_error_when_unconfigured() -> None:
    service = AIExplanationService(api_key=None, model="claude-test")
    with pytest.raises(AIExplanationConfigError):
        service.explain(_make_payment())


def test_explain_raises_call_error_on_client_exception() -> None:
    service = AIExplanationService(
        api_key="unused",
        model="claude-test",
        client=RaisingAnthropicClient(RuntimeError("boom")),
    )
    with pytest.raises(AIExplanationCallError):
        service.explain(_make_payment())


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


def test_endpoint_returns_404_when_payment_missing() -> None:
    app.dependency_overrides[get_ai_explanation_service] = lambda: AIExplanationService(
        api_key="unused", model="claude-test", client=FakeAnthropicClient(CANNED_JSON)
    )
    with TestClient(app) as client:
        resp = client.post("/api/demo-flow/payments/does-not-exist/ai-explanation")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_endpoint_returns_503_when_service_unconfigured() -> None:
    payment = _make_payment()
    get_payment_ledger().add_payments([payment])

    app.dependency_overrides[get_ai_explanation_service] = lambda: AIExplanationService(
        api_key=None, model="claude-test"
    )
    with TestClient(app) as client:
        resp = client.post(f"/api/demo-flow/payments/{payment.payment_id}/ai-explanation")
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_endpoint_returns_502_when_call_fails() -> None:
    payment = _make_payment()
    get_payment_ledger().add_payments([payment])
    service = AIExplanationService(
        api_key="unused",
        model="claude-test",
        client=RaisingAnthropicClient(RuntimeError("network down")),
    )
    app.dependency_overrides[get_ai_explanation_service] = lambda: service
    with TestClient(app) as client:
        resp = client.post(f"/api/demo-flow/payments/{payment.payment_id}/ai-explanation")
    assert resp.status_code == 502
    assert "network down" in resp.json()["detail"]


def test_endpoint_success_does_not_mutate_ledger() -> None:
    payment = _make_payment()
    ledger = get_payment_ledger()
    ledger.add_payments([payment])
    before_status = payment.current_status
    before_history = list(payment.status_history)
    before_evidence = list(payment.evidence)

    service = AIExplanationService(
        api_key="unused",
        model="claude-test",
        client=FakeAnthropicClient(CANNED_JSON),
    )
    app.dependency_overrides[get_ai_explanation_service] = lambda: service

    with TestClient(app) as client:
        resp = client.post(f"/api/demo-flow/payments/{payment.payment_id}/ai-explanation")

    assert resp.status_code == 200
    body = resp.json()
    assert body["payment_id"] == payment.payment_id
    assert body["provider"] == "anthropic"
    assert body["model"] == "claude-test"
    assert body["summary"]
    assert body["evidence_used"]
    assert body["limitations"]

    after = ledger.get_payment(payment.payment_id)
    assert after is not None
    assert after.current_status == before_status
    assert after.status_history == before_history
    assert after.evidence == before_evidence


def test_endpoint_handles_json_wrapped_in_code_fence() -> None:
    payment = _make_payment()
    get_payment_ledger().add_payments([payment])
    fenced = f"```json\n{CANNED_JSON}\n```"
    service = AIExplanationService(
        api_key="unused",
        model="claude-test",
        client=FakeAnthropicClient(fenced),
    )
    app.dependency_overrides[get_ai_explanation_service] = lambda: service
    with TestClient(app) as client:
        resp = client.post(f"/api/demo-flow/payments/{payment.payment_id}/ai-explanation")
    assert resp.status_code == 200
    assert resp.json()["summary"].startswith("Payment moved to beneficiary bank")


# ---------------------------------------------------------------------------
# System certificate store injection (PAYMENT_AGENT_USE_SYSTEM_CERTS)
# ---------------------------------------------------------------------------


class _StubAnthropic:
    """Stand-in for ``anthropic.Anthropic`` so no network call is attempted."""

    def __init__(self, *, api_key: str) -> None:  # noqa: D401 - simple stub
        self.api_key = api_key
        self.messages = _FakeMessages(CANNED_JSON, {})


def test_from_env_reads_use_system_certs_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unused")
    monkeypatch.setenv("PAYMENT_AGENT_USE_SYSTEM_CERTS", "true")
    service = AIExplanationService.from_env()
    assert service.use_system_certs is True

    monkeypatch.setenv("PAYMENT_AGENT_USE_SYSTEM_CERTS", "false")
    service = AIExplanationService.from_env()
    assert service.use_system_certs is False

    monkeypatch.delenv("PAYMENT_AGENT_USE_SYSTEM_CERTS", raising=False)
    service = AIExplanationService.from_env()
    assert service.use_system_certs is False


def test_get_client_injects_truststore_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import anthropic
    import truststore

    _reset_system_certs_injected_for_tests()
    calls: list[str] = []

    def _spy() -> None:
        calls.append("injected")

    monkeypatch.setattr(truststore, "inject_into_ssl", _spy)
    monkeypatch.setattr(anthropic, "Anthropic", _StubAnthropic)

    service = AIExplanationService(
        api_key="unused",
        model="claude-test",
        use_system_certs=True,
    )
    # Force real client construction (no injected client).
    client = service._get_client()
    assert isinstance(client, _StubAnthropic)
    assert calls == ["injected"]

    # Second call must not re-inject.
    service_two = AIExplanationService(
        api_key="unused",
        model="claude-test",
        use_system_certs=True,
    )
    service_two._get_client()
    assert calls == ["injected"]

    _reset_system_certs_injected_for_tests()


def test_get_client_does_not_inject_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import anthropic
    import truststore

    _reset_system_certs_injected_for_tests()
    calls: list[str] = []

    def _spy() -> None:
        calls.append("injected")

    monkeypatch.setattr(truststore, "inject_into_ssl", _spy)
    monkeypatch.setattr(anthropic, "Anthropic", _StubAnthropic)

    service = AIExplanationService(
        api_key="unused",
        model="claude-test",
        use_system_certs=False,
    )
    service._get_client()
    assert calls == []

    _reset_system_certs_injected_for_tests()


def test_injected_client_skips_truststore(monkeypatch: pytest.MonkeyPatch) -> None:
    """When a client is injected (as in most tests) we must not touch truststore."""
    import truststore

    _reset_system_certs_injected_for_tests()
    calls: list[str] = []
    monkeypatch.setattr(truststore, "inject_into_ssl", lambda: calls.append("x"))

    service = AIExplanationService(
        api_key=None,
        model="claude-test",
        client=FakeAnthropicClient(CANNED_JSON),
        use_system_certs=True,
    )
    service.explain(_make_payment())
    assert calls == []


# ---------------------------------------------------------------------------
# Output sanitization (Prompt 16 correction)
# ---------------------------------------------------------------------------


UNSAFE_CLAUDE_JSON = (
    '{"summary":"Payment cleared originating bank syntax checks successfully.",'
    '"status_explanation":"The payment has cleared and no funds have been '
    'debited yet.",'
    '"evidence_used":["CCD cleared originating bank checks",'
    '"Settlement summary received"],'
    '"limitations":["No funds have been transferred."],'
    '"recommended_action":"Wait; the payment cleared already.",'
    '"customer_safe_message":"Your payment cleared. No funds have been '
    'debited or transferred."}'
)


def _assert_no_unsafe_wording(*values: str) -> None:
    for value in values:
        lower = value.lower()
        assert "payment cleared" not in lower, value
        assert "payments cleared" not in lower, value
        assert "cleared originating" not in lower, value
        assert "has cleared" not in lower, value
        assert "have cleared" not in lower, value
        assert "was cleared" not in lower, value
        assert "were cleared" not in lower, value
        assert "no funds have been debited" not in lower, value
        assert "no funds have been transferred" not in lower, value
        assert "no funds have been credited" not in lower, value
        assert "funds have been debited" not in lower, value
        assert "funds have been transferred" not in lower, value


def test_sanitize_ai_text_rewrites_cleared_wording() -> None:
    cleaned = _sanitize_ai_text(
        "Payment cleared originating bank checks successfully.",
        "SENT TO SCHEME",
    )
    assert "cleared" not in cleaned.lower()
    assert "syntax validation" in cleaned.lower() or "passed" in cleaned.lower()


def test_sanitize_ai_text_replaces_unsupported_funds_sentence() -> None:
    cleaned = _sanitize_ai_text(
        "The scheme rejected the payment. No funds have been debited or transferred.",
        "REJECTED BY SCHEME",
    )
    assert "no funds have been debited" not in cleaned.lower()
    assert "rejected by the scheme" in cleaned.lower()


def test_sanitize_ai_text_uses_status_aware_safe_sentence() -> None:
    beneficiary = _sanitize_ai_text(
        "No funds have been transferred.", "WITH BENEFICIARY BANK"
    )
    assert "summary-level evidence only" in beneficiary.lower()

    scheme = _sanitize_ai_text(
        "No funds have been debited.", "REJECTED BY SCHEME"
    )
    assert "rejected by the scheme" in scheme.lower()


def test_sanitize_ai_text_is_noop_for_safe_wording() -> None:
    safe = "The payment progressed to the beneficiary bank after settlement summary."
    assert _sanitize_ai_text(safe, "WITH BENEFICIARY BANK") == safe


def test_explain_scrubs_unsafe_claude_output_before_returning() -> None:
    payment = _make_payment()
    service = AIExplanationService(
        api_key="unused",
        model="claude-test",
        client=FakeAnthropicClient(UNSAFE_CLAUDE_JSON),
    )

    result = service.explain(payment)

    _assert_no_unsafe_wording(
        result.summary,
        result.status_explanation,
        result.recommended_action,
        result.customer_safe_message,
        *result.evidence_used,
        *result.limitations,
    )


def test_endpoint_scrubs_unsafe_claude_output_before_returning() -> None:
    payment = _make_payment()
    get_payment_ledger().add_payments([payment])
    service = AIExplanationService(
        api_key="unused",
        model="claude-test",
        client=FakeAnthropicClient(UNSAFE_CLAUDE_JSON),
    )
    app.dependency_overrides[get_ai_explanation_service] = lambda: service

    with TestClient(app) as client:
        resp = client.post(f"/api/demo-flow/payments/{payment.payment_id}/ai-explanation")

    assert resp.status_code == 200
    body = resp.json()
    _assert_no_unsafe_wording(
        body["summary"],
        body["status_explanation"],
        body["recommended_action"],
        body["customer_safe_message"],
        *body["evidence_used"],
        *body["limitations"],
    )
    # Ledger untouched.
    after = get_payment_ledger().get_payment(payment.payment_id)
    assert after is not None
    assert after.current_status == payment.current_status
    assert after.status_history == payment.status_history
    assert after.evidence == payment.evidence


def test_endpoint_scrub_uses_beneficiary_safe_sentence_for_settlement_status() -> None:
    payment = _make_payment()  # current_status == WITH BENEFICIARY BANK
    get_payment_ledger().add_payments([payment])
    fund_leak_json = (
        '{"summary":"OK.",'
        '"status_explanation":"No funds have been debited or credited.",'
        '"evidence_used":["Settlement summary"],'
        '"limitations":["No return evidence yet."],'
        '"recommended_action":"Monitor.",'
        '"customer_safe_message":"Your payment cleared."}'
    )
    service = AIExplanationService(
        api_key="unused",
        model="claude-test",
        client=FakeAnthropicClient(fund_leak_json),
    )
    app.dependency_overrides[get_ai_explanation_service] = lambda: service

    with TestClient(app) as client:
        resp = client.post(f"/api/demo-flow/payments/{payment.payment_id}/ai-explanation")

    assert resp.status_code == 200
    body = resp.json()
    assert "summary-level evidence only" in body["status_explanation"].lower()
    assert "cleared" not in body["customer_safe_message"].lower()
