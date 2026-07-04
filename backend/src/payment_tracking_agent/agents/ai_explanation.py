"""Anthropic Claude AI explanation service (Prompt 16 / Prompt 17).

The service is evidence-grounded: it only explains deterministic ledger data
supplied to it. It never changes payment status, status history, or
evidence. Callers pass in a ``Payment`` snapshot and an optional
explanation ``preset`` and receive a typed ``AIExplanationResponse``.

Testable design:
- The Anthropic client can be injected via the ``client`` constructor
  argument so tests never touch real network.
- ``AIExplanationService.from_env()`` builds a service from environment
  variables ``ANTHROPIC_API_KEY`` and ``ANTHROPIC_MODEL``.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from payment_tracking_agent.models.ai_explanation import AIExplanationResponse
from payment_tracking_agent.models.ledger import Payment

DEFAULT_MODEL = "claude-3-5-sonnet-latest"


class ExplanationPreset(str, Enum):
    """Explanation style preset (Prompt 17)."""

    OPERATIONS = "operations"
    CUSTOMER_SAFE = "customer_safe"
    EXECUTIVE = "executive"


DEFAULT_PRESET = ExplanationPreset.OPERATIONS


_STATUS_GUIDANCE: dict[str, str] = {
    "WITH BENEFICIARY BANK": (
        "Status guidance for WITH BENEFICIARY BANK:\n"
        "- The CCD file passed bank-side syntax validation.\n"
        "- Settlement summary evidence was received for the batch.\n"
        "- The payment is currently treated as with the beneficiary bank.\n"
        "- Settlement summary is summary-level evidence only.\n"
        "- No payment-level clearing is claimed.\n"
        "- No NACHA return evidence has been matched for this payment.\n"
        "- Do not say 'cleared', 'settled at payment level', 'completed', "
        "'successfully paid', 'funds transferred', or 'funds credited'."
    ),
    "REJECTED BY SCHEME": (
        "Status guidance for REJECTED BY SCHEME:\n"
        "- The CCD file passed bank-side syntax validation.\n"
        "- A scheme-reject file matched this payment trace.\n"
        "- The payment was rejected at scheme validation.\n"
        "- The payment should be corrected and resubmitted in a new batch.\n"
        "- Do not infer a root cause beyond the exact reason in evidence.\n"
        "- Do not invent that a routing number is non-existent, an account "
        "is closed, or that the beneficiary bank rejected it.\n"
        "- Do not claim funds were or were not debited."
    ),
    "REJECTED BY BENEFICIARY BANK": (
        "Status guidance for REJECTED BY BENEFICIARY BANK:\n"
        "- The CCD file passed bank-side syntax validation.\n"
        "- Settlement summary evidence was received for the batch.\n"
        "- A NACHA return file later matched the original trace number.\n"
        "- The payment is rejected by the beneficiary bank.\n"
        "- The return reason code should drive the next action.\n"
        "- Do not overwrite or contradict scheme-reject evidence."
    ),
    "SENT TO SCHEME": (
        "Status guidance for SENT TO SCHEME:\n"
        "- The CCD file passed bank-side syntax validation.\n"
        "- The payment has been submitted to the scheme.\n"
        "- No downstream scheme, settlement, or return evidence has been "
        "received yet.\n"
        "- Do not claim clearing, settlement outcomes, or fund movement."
    ),
    "WITH BANK": (
        "Status guidance for WITH BANK:\n"
        "- The payment is currently with the bank.\n"
        "- Either bank-side syntax validation failed or a scheme reject "
        "requires bank correction, per the evidence.\n"
        "- The payment must be corrected and resubmitted."
    ),
}


_PRESET_GUIDANCE: dict[ExplanationPreset, str] = {
    ExplanationPreset.OPERATIONS: (
        "Explanation style: operations.\n"
        "- Audience is a bank operations analyst.\n"
        "- Use concise, professional ACH operations language.\n"
        "- Cite the specific evidence artifacts that support the current "
        "status.\n"
        "- Recommended action should be a concrete operations next step."
    ),
    ExplanationPreset.CUSTOMER_SAFE: (
        "Explanation style: customer_safe.\n"
        "- Audience is a bank customer, not an internal analyst.\n"
        "- Avoid internal jargon unless strictly necessary.\n"
        "- Do not use ACH file record codes or NACHA return codes as raw "
        "identifiers; describe them in plain language.\n"
        "- Do not claim or deny money movement.\n"
        "- Customer-safe message must be polite and non-alarming."
    ),
    ExplanationPreset.EXECUTIVE: (
        "Explanation style: executive.\n"
        "- Audience is a bank executive.\n"
        "- Keep the summary very short: current state, key evidence, and "
        "next step.\n"
        "- Prefer one to two sentences per field.\n"
        "- Do not include per-record technical detail."
    ),
}


SYSTEM_PROMPT = (
    "You are an ACH payment operations explanation assistant.\n"
    "You must only explain the deterministic evidence provided.\n"
    "Use the current_status field as the source of truth.\n"
    "Do not infer statuses from timestamps.\n"
    "Do not infer money movement.\n"
    "Do not infer customer risk history.\n"
    "Do not infer settlement amount reconciliation.\n"
    "Do not infer payment-level clearing from settlement summary.\n"
    "You must not invent payment status.\n"
    "You must not invent clearing.\n"
    "You must not invent return reasons.\n"
    "You must not invent customer history.\n"
    "You must not claim a payment is cleared from settlement summary evidence.\n"
    "Settlement summary is summary-level evidence only.\n"
    "\n"
    "Forbidden wording rules:\n"
    "- Do not say a payment is 'cleared', 'has cleared', 'was cleared', "
    "'were cleared', 'have cleared', 'payment cleared', or 'payments cleared'.\n"
    "- Do not say a payment is 'successfully paid', 'payment completed', or "
    "'settled at payment level'.\n"
    "- Do not use the word 'clearing' except in the specific caveat that "
    "settlement summary is NOT payment-level clearing evidence.\n"
    "- For CCD evidence, say 'bank-side syntax validation passed'. Do not say "
    "'cleared originating bank checks' or similar.\n"
    "- Do not state whether funds were debited, credited, transferred, moved, "
    "or not transferred unless that exact fact is present in the deterministic "
    "evidence provided. Do not add 'No funds have been debited/transferred/"
    "credited' or similar sentences.\n"
    "- Customer-safe messages must not claim or deny fund movement unless the "
    "deterministic evidence explicitly says so.\n"
    "- Do not include overly precise timing claims such as 'approximately N "
    "seconds after submission'. Use qualitative wording such as 'after CCD "
    "upload', 'later in the flow', 'after scheme-reject evidence was "
    "received', or 'after NACHA return evidence was received'.\n"
    "\n"
    "Return valid JSON only with keys: summary, status_explanation, "
    "evidence_used, limitations, recommended_action, customer_safe_message."
)


class AIExplanationConfigError(RuntimeError):
    """Raised when the AI provider is not configured (missing API key)."""


class AIExplanationCallError(RuntimeError):
    """Raised when the AI provider call fails at runtime."""


_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _env_flag_enabled(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY_ENV_VALUES


_system_certs_injected = False


def _inject_system_certs() -> None:
    """Route Python SSL through the operating system trust store.

    Idempotent. Never disables SSL verification. Callers must have opted in
    via ``PAYMENT_AGENT_USE_SYSTEM_CERTS=true`` or the equivalent
    constructor argument.
    """
    global _system_certs_injected
    if _system_certs_injected:
        return
    import truststore

    truststore.inject_into_ssl()
    _system_certs_injected = True


def _reset_system_certs_injected_for_tests() -> None:
    """Testing helper. Not used by production code."""
    global _system_certs_injected
    _system_certs_injected = False


class AIExplanationService:
    """Anthropic-backed AI explanation service.

    Explicit ``api_key`` and ``model`` arguments make the service easy to
    instantiate in tests without reading environment variables. ``client``
    can be any object exposing ``client.messages.create(**kwargs)``.

    When ``use_system_certs`` is true, ``truststore.inject_into_ssl()`` is
    called before constructing the real Anthropic client so that Python's
    ``ssl`` module uses the operating system certificate store. This is
    useful on corporate Windows machines where custom root CAs are only
    trusted by the OS. It never disables SSL verification.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        client: Any | None = None,
        use_system_certs: bool = False,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client
        self._use_system_certs = use_system_certs

    @classmethod
    def from_env(cls) -> AIExplanationService:
        return cls(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            model=os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL,
            use_system_certs=_env_flag_enabled("PAYMENT_AGENT_USE_SYSTEM_CERTS"),
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "anthropic"

    @property
    def use_system_certs(self) -> bool:
        return self._use_system_certs

    def is_configured(self) -> bool:
        return bool(self._api_key) or self._client is not None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise AIExplanationConfigError(
                "Claude AI explanation is not configured. "
                "Set ANTHROPIC_API_KEY and restart the backend."
            )
        if self._use_system_certs:
            _inject_system_certs()
        # Lazy import so tests never need the real SDK loaded at collection time.
        from anthropic import Anthropic

        self._client = Anthropic(api_key=self._api_key)
        return self._client

    def build_system_prompt(
        self, payment: Payment, preset: ExplanationPreset = DEFAULT_PRESET
    ) -> str:
        """Compose the base guardrails with status- and preset-specific text."""
        status_value = payment.current_status.value
        parts = [SYSTEM_PROMPT]
        status_guidance = _STATUS_GUIDANCE.get(status_value)
        if status_guidance:
            parts.append(status_guidance)
        parts.append(_PRESET_GUIDANCE[preset])
        return "\n\n".join(parts)

    def build_user_prompt(
        self, payment: Payment, preset: ExplanationPreset = DEFAULT_PRESET
    ) -> str:
        """Assemble the compact evidence packet the prompt spec calls for."""
        status_history = [h.model_dump(mode="json") for h in payment.status_history]
        evidence = [e.model_dump(mode="json") for e in payment.evidence]
        packet: dict[str, Any] = {
            "current_status": payment.current_status.value,
            "payment_identity": {
                "payment_id": payment.payment_id,
                "individual_id_number": payment.individual_id_number,
                "individual_name": payment.individual_name,
                "receiving_dfi_identification": payment.receiving_dfi_identification,
                "masked_account_number": payment.masked_account_number,
            },
            "amount_cents": payment.amount_cents,
            "batch": {
                "batch_key": payment.batch_key,
                "source_file": payment.source_file,
            },
            "trace_number": payment.trace_number,
            "status_history_chronological": status_history,
            "evidence_chronological": evidence,
            "known_limitations": [
                "Settlement summary is summary-level evidence only.",
                "No payment-level clearing is claimed from settlement summary.",
                "Return files may arrive in later cycles and are not guaranteed to arrive.",
            ],
            "allowed_conclusions": [
                "Restate the current_status.",
                "Describe the evidence that supports the current_status.",
                "Recommend an operations next step consistent with the evidence.",
            ],
            "forbidden_conclusions": [
                "Do not infer payment-level clearing from settlement summary.",
                "Do not infer money movement.",
                "Do not infer customer risk history from a single payment.",
                "Do not infer settlement amount reconciliation.",
                "Do not infer statuses from timestamps.",
            ],
            "explanation_preset": preset.value,
        }
        return (
            "Explain this ACH payment based only on the deterministic evidence "
            "packet below. Return valid JSON only with keys: summary, "
            "status_explanation, evidence_used, limitations, "
            "recommended_action, customer_safe_message.\n\n"
            f"Evidence packet: {json.dumps(packet, default=str)}"
        )

    def explain(
        self,
        payment: Payment,
        preset: ExplanationPreset = DEFAULT_PRESET,
    ) -> AIExplanationResponse:
        client = self._get_client()
        system_prompt = self.build_system_prompt(payment, preset)
        user_prompt = self.build_user_prompt(payment, preset)
        try:
            message = client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except AIExplanationConfigError:
            raise
        except Exception as exc:  # anthropic.APIError, network, etc.
            raise AIExplanationCallError(str(exc)) from exc

        data = _parse_response_json(_extract_text(message))
        status_value = payment.current_status.value

        return AIExplanationResponse(
            payment_id=payment.payment_id,
            provider=self.provider,
            model=self._model,
            summary=_sanitize_ai_text(_coerce_str(data.get("summary")), status_value),
            status_explanation=_sanitize_ai_text(
                _coerce_str(data.get("status_explanation")), status_value
            ),
            evidence_used=[
                _sanitize_ai_text(item, status_value)
                for item in _coerce_str_list(data.get("evidence_used"))
            ],
            limitations=[
                _sanitize_ai_text(item, status_value)
                for item in _coerce_str_list(data.get("limitations"))
            ],
            recommended_action=_sanitize_ai_text(
                _coerce_str(data.get("recommended_action")), status_value
            ),
            customer_safe_message=_sanitize_ai_text(
                _coerce_str(data.get("customer_safe_message")), status_value
            ),
            generated_at=datetime.now(timezone.utc),
        )


def _extract_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            text = getattr(block, "text", None)
            if text is None and isinstance(block, dict):
                text = block.get("text")
            if text:
                parts.append(str(text))
        return "".join(parts)
    return ""


def _parse_response_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if not cleaned:
        return {}
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if item is not None]


# ---------------------------------------------------------------------------
# Output sanitization
# ---------------------------------------------------------------------------
#
# Claude sometimes drifts into unsafe wording even after the system prompt
# forbids it. We defensively scrub the six string outputs before they leave
# the backend. Sanitization only rewrites language; it never changes payment
# status, status history, or evidence in the ledger.

_CLEARED_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    # Handle "cleared originating" first so "Payment cleared originating bank
    # checks" becomes "Payment passed originating bank syntax validation on
    # checks" rather than losing the "originating" cue to the broader rule.
    (
        re.compile(r"\bcleared\s+(the\s+)?originating\s+bank(?:'s)?\b", re.IGNORECASE),
        r"passed \1originating bank syntax validation on",
    ),
    (
        re.compile(r"\bcleared\s+(the\s+)?originating\b", re.IGNORECASE),
        r"passed \1originating",
    ),
    (re.compile(r"\bpayment[s]?\s+cleared\b", re.IGNORECASE), "payment progressed"),
    (re.compile(r"\bclearing\s+checks\b", re.IGNORECASE), "syntax validation checks"),
    (re.compile(r"\bhas\s+cleared\b", re.IGNORECASE), "has progressed"),
    (re.compile(r"\bhave\s+cleared\b", re.IGNORECASE), "have progressed"),
    (re.compile(r"\bwas\s+cleared\b", re.IGNORECASE), "was progressed"),
    (re.compile(r"\bwere\s+cleared\b", re.IGNORECASE), "were progressed"),
]

_UNSUPPORTED_FUNDS_REGEX = re.compile(
    r"\b(?:no\s+)?funds?\s+"
    r"(?:have\s+been\s+|has\s+been\s+|were\s+|was\s+|are\s+|is\s+|being\s+|"
    r"successfully\s+)?"
    r"(?:debited|credited|transferred|moved)\b",
    re.IGNORECASE,
)

_UNSUPPORTED_OUTCOME_REGEX = re.compile(
    r"\b(?:"
    r"successfully\s+paid|"
    r"payment[s]?\s+completed|"
    r"payment[s]?\s+successfully\s+completed|"
    r"settled\s+at\s+payment\s+level|"
    r"settlement\s+is\s+complete"
    r")\b",
    re.IGNORECASE,
)

_TIMING_CLAIM_REGEX = re.compile(
    r"\b(?:approximately|roughly|about|around)\s+\d+(?:\.\d+)?\s+"
    r"(?:second|sec|minute|min|hour|hr|day)s?\b"
    r"(?:\s+(?:after|before|since|following)\s+\S+(?:\s+\S+)?)?",
    re.IGNORECASE,
)

_TIMING_SAFE_PHRASE = "later in the flow"

_SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+")

_SAFE_STATUS_SENTENCES: dict[str, str] = {
    "REJECTED BY SCHEME": (
        "The available evidence shows the payment was rejected by the scheme "
        "before beneficiary-bank processing."
    ),
    "REJECTED BY BENEFICIARY BANK": (
        "The available evidence shows a NACHA return file matched the "
        "original trace and the payment is now with the bank for follow-up."
    ),
    "WITH BENEFICIARY BANK": (
        "Settlement summary is summary-level evidence only and does not "
        "confirm payment-level fund movement."
    ),
    "SENT TO SCHEME": (
        "The available evidence shows the payment was submitted to the "
        "scheme; no downstream evidence has been received yet."
    ),
    "WITH BANK": (
        "The available evidence shows the payment is with the bank "
        "pending correction or resubmission."
    ),
}

_DEFAULT_SAFE_SENTENCE = (
    "The available evidence does not describe fund movement."
)


def _safe_status_sentence(status_value: str) -> str:
    return _SAFE_STATUS_SENTENCES.get(status_value, _DEFAULT_SAFE_SENTENCE)


def _sanitize_ai_text(text: str, status_value: str) -> str:
    """Scrub unsafe AI wording before it leaves the backend.

    - Rewrites "cleared"/"clearing" verbs into ACH-safe language.
    - Rewrites overly precise timing claims into qualitative wording.
    - Replaces sentences that make unsupported fund-movement or completion
      claims with a status-aware safe sentence.

    Never mutates the payment ledger.
    """
    if not text:
        return text
    result = text
    for pattern, replacement in _CLEARED_REPLACEMENTS:
        result = pattern.sub(replacement, result)

    result = _TIMING_CLAIM_REGEX.sub(_TIMING_SAFE_PHRASE, result)

    if _UNSUPPORTED_FUNDS_REGEX.search(result) or _UNSUPPORTED_OUTCOME_REGEX.search(
        result
    ):
        safe_sentence = _safe_status_sentence(status_value)
        sentences = _SENTENCE_SPLIT_REGEX.split(result)
        rewritten: list[str] = []
        replaced = False
        for sentence in sentences:
            if _UNSUPPORTED_FUNDS_REGEX.search(
                sentence
            ) or _UNSUPPORTED_OUTCOME_REGEX.search(sentence):
                if not replaced:
                    rewritten.append(safe_sentence)
                    replaced = True
                # Drop subsequent offending sentences to avoid duplication.
            else:
                rewritten.append(sentence)
        result = " ".join(part for part in rewritten if part).strip()

    return result


_service_singleton: AIExplanationService | None = None


def get_ai_explanation_service() -> AIExplanationService:
    """FastAPI dependency providing a cached service built from env vars."""
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = AIExplanationService.from_env()
    return _service_singleton


def reset_ai_explanation_service() -> None:
    """Testing helper. Not used by production code."""
    global _service_singleton
    _service_singleton = None

