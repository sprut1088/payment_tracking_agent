"""AI payment / customer / batch risk classification service.

This service classifies three scopes:

1. Payment risk (lifecycle stamped)
2. Customer risk (history trend)
3. Batch risk (CCD validation quality)

Important behavioral rule for CCD upload:

- CCD_UPLOAD payment risk is based on customer history + batch validation
  findings only.
- It must not use normal lifecycle uncertainty drivers such as
  "SENT TO SCHEME only", "no settlement evidence yet", or
  "no return evidence yet".

Deterministic ledger statuses remain authoritative. AI never mutates
status/history/evidence and never determines payment status.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from payment_tracking_agent.agents.ai_explanation import (
    _env_flag_enabled,
    _extract_text,
    _inject_system_certs,
    _parse_response_json,
    _sanitize_ai_text,
)
from payment_tracking_agent.models.ai_risk import (
    BatchRiskClassification,
    ClearingConfidence,
    CustomerRiskClassification,
    OutcomeAlignment,
    PriorPredictionOutcome,
    RiskBand,
    RiskClassification,
    RiskClassificationTrigger,
)
from payment_tracking_agent.models.ledger import Payment, PaymentStatus
from payment_tracking_agent.services.batch_validation import BatchValidationSummary
from payment_tracking_agent.services.customer_history import CustomerHistorySummary

DEFAULT_MODEL = "claude-3-5-sonnet-latest"
FALLBACK_PROVIDER = "fallback"
FALLBACK_MODEL = "deterministic"

SYSTEM_PROMPT = (
    "You are an ACH operations AI risk classification assistant.\n"
    "You classify three scopes: payment risk, customer risk, and batch risk.\n"
    "You do not classify credit risk.\n"
    "You do not classify fraud risk.\n"
    "You do not infer customer financial health.\n"
    "You do not infer customer history beyond provided demo history.\n"
    "You do not determine payment status.\n"
    "You do not infer money movement.\n"
    "Do not claim funds were credited, debited, or transferred.\n"
    "Do not claim payment-level clearing from settlement summary.\n"
    "Settlement summary is summary-level evidence only.\n"
    "Clearing confidence is operational AI confidence only.\n"
    "\n"
    "For CCD_UPLOAD payment classification: use customer history and batch "
    "validation findings only. Do NOT use missing downstream evidence as a "
    "risk driver.\n"
    "\n"
    "Return valid JSON only."
)


@dataclass(frozen=True)
class PaymentClassificationInputs:
    customer_summary: CustomerHistorySummary
    batch_summary: BatchValidationSummary


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class AIRiskClassificationService:
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
    def from_env(cls) -> AIRiskClassificationService:
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

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            return None
        if self._use_system_certs:
            _inject_system_certs()
        from anthropic import Anthropic

        self._client = Anthropic(api_key=self._api_key)
        return self._client

    # ------------------------------------------------------------------
    # Public classification entrypoints
    # ------------------------------------------------------------------

    def classify_customer(
        self,
        summary: CustomerHistorySummary,
        *,
        now: datetime | None = None,
    ) -> CustomerRiskClassification:
        client = self._get_client()
        if client is None:
            return _fallback_customer(summary, now=now)
        try:
            data = self._call_ai(
                client,
                {
                    "scope": "customer",
                    "summary": _customer_packet(summary),
                    "json_contract": {
                        "risk_score": "0-100 int",
                        "risk_band": "LOW|MEDIUM|HIGH",
                        "confidence_score": "0-100 int",
                        "summary": "string",
                        "risk_drivers": "string[]",
                        "evidence_used": "string[]",
                        "limitations": "string[]",
                        "recommendation": "string",
                    },
                },
            )
        except Exception:
            return _fallback_customer(summary, now=now)
        return _customer_from_ai(data, summary, model=self._model, now=now)

    def classify_batch(
        self,
        summary: BatchValidationSummary,
        *,
        now: datetime | None = None,
    ) -> BatchRiskClassification:
        client = self._get_client()
        if client is None:
            return _fallback_batch(summary, now=now)
        try:
            data = self._call_ai(
                client,
                {
                    "scope": "batch",
                    "summary": _batch_packet(summary),
                    "json_contract": {
                        "risk_score": "0-100 int",
                        "risk_band": "LOW|MEDIUM|HIGH",
                        "confidence_score": "0-100 int",
                        "summary": "string",
                        "risk_drivers": "string[]",
                        "validation_findings": "string[]",
                        "evidence_used": "string[]",
                        "limitations": "string[]",
                        "recommendation": "string",
                    },
                },
            )
        except Exception:
            return _fallback_batch(summary, now=now)
        return _batch_from_ai(data, summary, model=self._model, now=now)

    def classify_payment(
        self,
        payment: Payment,
        trigger: RiskClassificationTrigger,
        *,
        customer_classification: CustomerRiskClassification,
        batch_classification: BatchRiskClassification,
        prior_classification: RiskClassification | None = None,
        now: datetime | None = None,
    ) -> RiskClassification:
        client = self._get_client()
        if client is None:
            return _fallback_payment(
                payment,
                trigger,
                customer_classification=customer_classification,
                batch_classification=batch_classification,
                prior_classification=prior_classification,
                now=now,
            )

        packet = {
            "scope": "payment",
            "trigger": trigger.value,
            "payment": {
                "payment_id": payment.payment_id,
                "current_status": payment.current_status.value,
                "trace_number": payment.trace_number,
                "amount_cents": payment.amount_cents,
            },
            "customer_risk": customer_classification.model_dump(mode="json"),
            "batch_risk": batch_classification.model_dump(mode="json"),
            "prior_payment_classification": (
                prior_classification.model_dump(mode="json")
                if prior_classification
                else None
            ),
            "status_history": [
                event.model_dump(mode="json") for event in payment.status_history
            ],
            "evidence": [item.model_dump(mode="json") for item in payment.evidence],
            "ccd_upload_guardrail": (
                "For CCD_UPLOAD, do not cite pending settlement/return evidence. "
                "Do not cite earliest pipeline status as a risk driver."
            ),
            "json_contract": {
                "risk_score": "0-100 int",
                "risk_band": "LOW|MEDIUM|HIGH",
                "clearing_confidence": "LOW|MEDIUM|HIGH",
                "summary": "string",
                "risk_drivers": "string[]",
                "evidence_used": "string[]",
                "recommendation": "string",
            },
        }

        try:
            data = self._call_ai(client, packet)
        except Exception:
            return _fallback_payment(
                payment,
                trigger,
                customer_classification=customer_classification,
                batch_classification=batch_classification,
                prior_classification=prior_classification,
                now=now,
            )

        return _payment_from_ai(
            data,
            payment,
            trigger,
            customer_classification=customer_classification,
            batch_classification=batch_classification,
            prior_classification=prior_classification,
            model=self._model,
            now=now,
        )

    # ------------------------------------------------------------------
    # Anthropic call wrapper
    # ------------------------------------------------------------------

    def _call_ai(self, client: Any, packet: dict[str, Any]) -> dict[str, Any]:
        message = client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Classify ACH operational risk from the deterministic "
                        "packet below. Return valid JSON only.\n\n"
                        + json.dumps(packet, default=str)
                    ),
                }
            ],
        )
        return _parse_response_json(_extract_text(message))


# ---------------------------------------------------------------------------
# Fallback logic (deterministic, no network)
# ---------------------------------------------------------------------------


def _fallback_customer(
    summary: CustomerHistorySummary,
    *,
    now: datetime | None,
) -> CustomerRiskClassification:
    if summary.rejections_last_7d >= 2:
        risk_score = 84
        band = RiskBand.HIGH
        confidence = 88
        rec = "Review recurring rejection root cause before new submission."
        drivers = [
            f"Customer had {summary.rejections_last_7d} rejected payments in the last 7 days.",
        ]
        if summary.common_reason_codes:
            drivers.append(
                "Repeated recent rejection reason(s): "
                + ", ".join(summary.common_reason_codes[:2])
                + "."
            )
    elif summary.rejections_last_30d >= 2 or summary.rejections_last_90d >= 2:
        risk_score = 62
        band = RiskBand.MEDIUM
        confidence = 82
        rec = "Review recent rejection trend and correct known recurring issues."
        drivers = [
            (
                "Customer had multiple rejected payments in recent history "
                f"(30d={summary.rejections_last_30d}, 90d={summary.rejections_last_90d})."
            )
        ]
    else:
        risk_score = 18
        band = RiskBand.LOW
        confidence = 90
        rec = "Proceed with normal monitoring; no recent rejection trend detected."
        drivers = ["No recent failed payments in available customer history."]

    evidence = [
        f"Customer rejection counts: 7d={summary.rejections_last_7d}, 30d={summary.rejections_last_30d}, 90d={summary.rejections_last_90d}.",
    ]
    if summary.latest_rejection_at:
        evidence.append(
            "Latest rejection date: " + summary.latest_rejection_at.isoformat()
        )
    if summary.common_reason_codes:
        evidence.append(
            "Common rejection reason codes: " + ", ".join(summary.common_reason_codes)
        )

    return CustomerRiskClassification(
        customer_id=summary.customer_id,
        customer_name=summary.customer_name,
        risk_score=risk_score,
        risk_band=band,
        confidence_score=confidence,
        summary=_sanitize_risk_text(
            _coerce_str(
                f"{band.value.title()} customer risk from historical rejection trend."
            ),
            "WITH BANK",
        ),
        risk_drivers=[_sanitize_risk_text(d, "WITH BANK") for d in drivers],
        evidence_used=evidence,
        limitations=[
            "Customer risk uses demo historical rejection data only.",
            "No database-backed full customer history is implemented yet.",
        ],
        recommendation=_sanitize_risk_text(rec, "WITH BANK"),
        classified_at=now or datetime.now(timezone.utc),
        provider=FALLBACK_PROVIDER,
        model=FALLBACK_MODEL,
    )


def _fallback_batch(
    summary: BatchValidationSummary,
    *,
    now: datetime | None,
) -> BatchRiskClassification:
    severity = summary.severity()
    if severity == "HIGH":
        risk_score = 86
        band = RiskBand.HIGH
        confidence = 88
        rec = "Fix validation findings before submission or resubmission."
    elif severity == "MEDIUM":
        risk_score = 58
        band = RiskBand.MEDIUM
        confidence = 82
        rec = "Review warnings and monitor closely for downstream rejects."
    else:
        risk_score = 22
        band = RiskBand.LOW
        confidence = 91
        rec = "Proceed; maintain standard batch monitoring controls."

    findings = [*summary.validation_findings, *summary.parser_errors]
    if not findings:
        findings = ["No deterministic CCD validation findings recorded."]

    return BatchRiskClassification(
        batch_key=summary.batch_key,
        source_file=summary.source_file,
        risk_score=risk_score,
        risk_band=band,
        confidence_score=confidence,
        summary=_sanitize_risk_text(
            (
                f"{band.value.title()} batch risk from available CCD validation checks."
            ),
            "WITH BANK",
        ),
        risk_drivers=[
            _sanitize_risk_text(
                f"Bank-side syntax validation {'passed' if summary.syntax_valid else 'failed'}.",
                "WITH BANK",
            ),
            _sanitize_risk_text(
                f"File parse result: {'success' if summary.file_parsed else 'failure'}; "
                f"records accepted: {summary.accepted_count}/{summary.payment_count}.",
                "WITH BANK",
            ),
        ],
        validation_findings=findings,
        evidence_used=[
            f"Parsed CCD source file: {summary.source_file}",
            f"payment_count={summary.payment_count}",
            f"accepted_count={summary.accepted_count}",
        ],
        limitations=[
            (
                "Batch risk is based on available CCD validation checks. Full "
                "FedACH/NACHA syntax correction workflow is planned as a "
                "future enhancement."
            )
        ],
        recommendation=_sanitize_risk_text(rec, "WITH BANK"),
        classified_at=now or datetime.now(timezone.utc),
        provider=FALLBACK_PROVIDER,
        model=FALLBACK_MODEL,
    )


def _payment_from_customer_batch(
    customer_classification: CustomerRiskClassification,
    batch_classification: BatchRiskClassification,
) -> tuple[int, RiskBand, ClearingConfidence]:
    # Weighted blend: customer trend (60%) + batch quality (40%).
    combined = round(
        customer_classification.risk_score * 0.6
        + batch_classification.risk_score * 0.4
    )
    if combined >= 75:
        band = RiskBand.HIGH
    elif combined >= 45:
        band = RiskBand.MEDIUM
    else:
        band = RiskBand.LOW

    # Higher risk implies lower operational clearing confidence.
    if combined >= 75:
        confidence = ClearingConfidence.LOW
    elif combined >= 45:
        confidence = ClearingConfidence.MEDIUM
    else:
        confidence = ClearingConfidence.HIGH
    return combined, band, confidence


def _fallback_payment(
    payment: Payment,
    trigger: RiskClassificationTrigger,
    *,
    customer_classification: CustomerRiskClassification,
    batch_classification: BatchRiskClassification,
    prior_classification: RiskClassification | None,
    now: datetime | None,
) -> RiskClassification:
    if trigger == RiskClassificationTrigger.CCD_UPLOAD:
        score, band, confidence = _payment_from_customer_batch(
            customer_classification, batch_classification
        )
        drivers = [
            (
                "Customer historical rejection trend: "
                f"{customer_classification.risk_band.value} "
                f"(score {customer_classification.risk_score})."
            ),
            (
                "Batch validation quality: "
                f"{batch_classification.risk_band.value} "
                f"(score {batch_classification.risk_score})."
            ),
        ]
        summary = (
            "CCD upload payment risk predicted from customer history and "
            "batch validation findings."
        )
        recommendation = (
            "If known recurring customer or validation issues exist, review and "
            "correct before submission."
        )
        evidence = [
            "Customer risk classification from demo historical rejection trend.",
            "Batch risk classification from deterministic CCD validation summary.",
        ]
        prior_prediction = None
    elif trigger == RiskClassificationTrigger.SETTLEMENT_OR_SCHEME_REJECT:
        if payment.current_status == PaymentStatus.REJECTED_BY_SCHEME:
            score, band, confidence = 88, RiskBand.HIGH, ClearingConfidence.LOW
            drivers = [
                "Scheme reject evidence matched this payment.",
                "Payment requires correction before any resubmission.",
            ]
            summary = (
                "Current operational risk is high after scheme reject evidence."
            )
            recommendation = "Correct scheme findings and resubmit in a new batch."
        else:
            score, band, confidence = 42, RiskBand.MEDIUM, ClearingConfidence.MEDIUM
            drivers = [
                "Settlement summary evidence received for the batch.",
                "No payment-level clearing is claimed from settlement summary.",
            ]
            summary = (
                "Current operational risk updated after settlement summary evidence."
            )
            recommendation = "Continue monitoring for return evidence in later cycles."
        evidence = [item.summary for item in payment.evidence[-2:]]
        prior_prediction = None
    else:
        score, band, confidence = 92, RiskBand.HIGH, ClearingConfidence.LOW
        drivers = [
            "NACHA return evidence matched this payment's original trace number.",
            "Actual adverse outcome confirmed by beneficiary-bank return evidence.",
        ]
        summary = "Payment risk is high after confirmed NACHA return outcome."
        recommendation = "Review return reason and correct issue before resubmission."
        evidence = [item.summary for item in payment.evidence[-2:]]
        prior_prediction = _build_prior_prediction(prior_classification, payment)

    return RiskClassification(
        trigger=trigger,
        risk_score=score,
        risk_band=band,
        clearing_confidence=confidence,
        summary=_sanitize_risk_text(summary, payment.current_status.value),
        risk_drivers=[
            _sanitize_risk_text(driver, payment.current_status.value)
            for driver in _remove_forbidden_ccd_upload_drivers(trigger, drivers)
        ],
        evidence_used=[
            _sanitize_risk_text(item, payment.current_status.value) for item in evidence
        ],
        recommendation=_sanitize_risk_text(
            recommendation, payment.current_status.value
        ),
        prior_prediction=prior_prediction,
        provider=FALLBACK_PROVIDER,
        model=FALLBACK_MODEL,
        classified_at=now or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# AI → typed coercion
# ---------------------------------------------------------------------------


def _customer_from_ai(
    data: dict[str, Any],
    summary: CustomerHistorySummary,
    *,
    model: str,
    now: datetime | None,
) -> CustomerRiskClassification:
    fallback = _fallback_customer(summary, now=now)
    risk_score = _coerce_int(data.get("risk_score"), fallback.risk_score)
    risk_band = _coerce_band(data.get("risk_band"), fallback.risk_band)
    confidence_score = _coerce_int(
        data.get("confidence_score"), fallback.confidence_score
    )
    return CustomerRiskClassification(
        customer_id=summary.customer_id,
        customer_name=summary.customer_name,
        risk_score=risk_score,
        risk_band=risk_band,
        confidence_score=confidence_score,
        summary=_sanitize_risk_text(
            _coerce_str(data.get("summary")) or fallback.summary,
            "WITH BANK",
        ),
        risk_drivers=_coerce_str_list(data.get("risk_drivers"))
        or fallback.risk_drivers,
        evidence_used=_coerce_str_list(data.get("evidence_used"))
        or fallback.evidence_used,
        limitations=_coerce_str_list(data.get("limitations"))
        or fallback.limitations,
        recommendation=_sanitize_risk_text(
            _coerce_str(data.get("recommendation")) or fallback.recommendation,
            "WITH BANK",
        ),
        classified_at=now or datetime.now(timezone.utc),
        provider="anthropic",
        model=model,
    )


def _batch_from_ai(
    data: dict[str, Any],
    summary: BatchValidationSummary,
    *,
    model: str,
    now: datetime | None,
) -> BatchRiskClassification:
    fallback = _fallback_batch(summary, now=now)
    risk_score = _coerce_int(data.get("risk_score"), fallback.risk_score)
    risk_band = _coerce_band(data.get("risk_band"), fallback.risk_band)
    confidence_score = _coerce_int(
        data.get("confidence_score"), fallback.confidence_score
    )
    return BatchRiskClassification(
        batch_key=summary.batch_key,
        source_file=summary.source_file,
        risk_score=risk_score,
        risk_band=risk_band,
        confidence_score=confidence_score,
        summary=_sanitize_risk_text(
            _coerce_str(data.get("summary")) or fallback.summary,
            "WITH BANK",
        ),
        risk_drivers=_coerce_str_list(data.get("risk_drivers"))
        or fallback.risk_drivers,
        validation_findings=_coerce_str_list(data.get("validation_findings"))
        or fallback.validation_findings,
        evidence_used=_coerce_str_list(data.get("evidence_used"))
        or fallback.evidence_used,
        limitations=_coerce_str_list(data.get("limitations"))
        or fallback.limitations,
        recommendation=_sanitize_risk_text(
            _coerce_str(data.get("recommendation")) or fallback.recommendation,
            "WITH BANK",
        ),
        classified_at=now or datetime.now(timezone.utc),
        provider="anthropic",
        model=model,
    )


def _payment_from_ai(
    data: dict[str, Any],
    payment: Payment,
    trigger: RiskClassificationTrigger,
    *,
    customer_classification: CustomerRiskClassification,
    batch_classification: BatchRiskClassification,
    prior_classification: RiskClassification | None,
    model: str,
    now: datetime | None,
) -> RiskClassification:
    fallback = _fallback_payment(
        payment,
        trigger,
        customer_classification=customer_classification,
        batch_classification=batch_classification,
        prior_classification=prior_classification,
        now=now,
    )

    score = _coerce_int(data.get("risk_score"), fallback.risk_score)
    band = _coerce_band(data.get("risk_band"), fallback.risk_band)
    confidence = _coerce_confidence(
        data.get("clearing_confidence"), fallback.clearing_confidence
    )
    drivers = _coerce_str_list(data.get("risk_drivers")) or fallback.risk_drivers
    drivers = _remove_forbidden_ccd_upload_drivers(trigger, drivers)

    return RiskClassification(
        trigger=trigger,
        risk_score=score,
        risk_band=band,
        clearing_confidence=confidence,
        summary=_sanitize_risk_text(
            _coerce_str(data.get("summary")) or fallback.summary,
            payment.current_status.value,
        ),
        risk_drivers=[
            _sanitize_risk_text(driver, payment.current_status.value)
            for driver in drivers
        ],
        evidence_used=[
            _sanitize_risk_text(item, payment.current_status.value)
            for item in (_coerce_str_list(data.get("evidence_used")) or fallback.evidence_used)
        ],
        recommendation=_sanitize_risk_text(
            _coerce_str(data.get("recommendation")) or fallback.recommendation,
            payment.current_status.value,
        ),
        prior_prediction=(
            _build_prior_prediction(prior_classification, payment)
            if trigger == RiskClassificationTrigger.NACHA_RETURN
            else None
        ),
        provider="anthropic",
        model=model,
        classified_at=now or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Shared helpers / sanitization
# ---------------------------------------------------------------------------


def _customer_packet(summary: CustomerHistorySummary) -> dict[str, Any]:
    return {
        "customer_id": summary.customer_id,
        "customer_name": summary.customer_name,
        "rejections_last_7d": summary.rejections_last_7d,
        "rejections_last_30d": summary.rejections_last_30d,
        "rejections_last_90d": summary.rejections_last_90d,
        "common_reason_codes": summary.common_reason_codes,
        "latest_rejection_at": (
            summary.latest_rejection_at.isoformat()
            if summary.latest_rejection_at
            else None
        ),
        "open_rejected_payments": summary.open_rejected_payments,
    }


def _batch_packet(summary: BatchValidationSummary) -> dict[str, Any]:
    return {
        "batch_key": summary.batch_key,
        "source_file": summary.source_file,
        "file_parsed": summary.file_parsed,
        "payment_count": summary.payment_count,
        "accepted_count": summary.accepted_count,
        "syntax_valid": summary.syntax_valid,
        "parser_errors": summary.parser_errors,
        "validation_findings": summary.validation_findings,
    }


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if item is not None]


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        iv = int(value)
    except Exception:
        return fallback
    return max(0, min(100, iv))


def _coerce_band(value: Any, fallback: RiskBand) -> RiskBand:
    text = _coerce_str(value).upper()
    if text in {"LOW", "MEDIUM", "HIGH"}:
        return RiskBand(text)
    return fallback


def _coerce_confidence(
    value: Any,
    fallback: ClearingConfidence,
) -> ClearingConfidence:
    text = _coerce_str(value).upper()
    if text in {"LOW", "MEDIUM", "HIGH"}:
        return ClearingConfidence(text)
    return fallback


_FORBIDDEN_CCD_UPLOAD_DRIVER_PATTERNS = [
    re.compile(r"\bsent\s+to\s+scheme\s+only\b", re.IGNORECASE),
    re.compile(r"\bno\s+settlement\s+evidence\s+(?:received\s+)?yet\b", re.IGNORECASE),
    re.compile(r"\bno\s+return\s+evidence\s+(?:received\s+)?yet\b", re.IGNORECASE),
    re.compile(r"\blifecycle\s+evidence\s+pending\b", re.IGNORECASE),
    re.compile(r"\bearliest\s+pipeline\s+status\b", re.IGNORECASE),
]


def _remove_forbidden_ccd_upload_drivers(
    trigger: RiskClassificationTrigger,
    drivers: list[str],
) -> list[str]:
    if trigger != RiskClassificationTrigger.CCD_UPLOAD:
        return drivers
    filtered: list[str] = []
    for driver in drivers:
        if any(p.search(driver) for p in _FORBIDDEN_CCD_UPLOAD_DRIVER_PATTERNS):
            continue
        filtered.append(driver)
    return filtered


_RISK_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bfraud\s+risk\b", re.IGNORECASE), "operational risk"),
    (re.compile(r"\bcredit\s+risk\b", re.IGNORECASE), "operational risk"),
    (re.compile(r"\bcustomer\s+is\s+risky\b", re.IGNORECASE), "customer has operational follow-up risk"),
    (re.compile(r"\bcustomer\s+lacks\s+funds\b", re.IGNORECASE), "beneficiary-bank return history indicates prior failures"),
    (re.compile(r"\bpayment\s+cleared\b", re.IGNORECASE), "payment progressed"),
    (re.compile(r"\bsuccessfully\s+paid\b", re.IGNORECASE), "processed with available evidence"),
    (re.compile(r"\bpayment\s+completed\b", re.IGNORECASE), "payment progressed"),
    (re.compile(r"\bfunds\s+credited\b", re.IGNORECASE), "fund-movement evidence"),
    (re.compile(r"\bfunds\s+transferred\b", re.IGNORECASE), "fund-movement evidence"),
    (re.compile(r"\bfunds\s+debited\b", re.IGNORECASE), "fund-movement evidence"),
]


def _sanitize_risk_text(text: str, status_value: str) -> str:
    result = _sanitize_ai_text(text, status_value)
    for pattern, replacement in _RISK_REPLACEMENTS:
        result = pattern.sub(replacement, result)
    return result


def _build_prior_prediction(
    prior_classification: RiskClassification | None,
    payment: Payment,
) -> PriorPredictionOutcome:
    if prior_classification is None:
        return PriorPredictionOutcome(
            prior_risk_score=None,
            prior_risk_band=None,
            prior_clearing_confidence=None,
            actual_outcome_status=payment.current_status.value,
            outcome_alignment=OutcomeAlignment.NOT_APPLICABLE,
            narrative="No prior payment risk classification was available for comparison.",
        )

    if prior_classification.risk_band == RiskBand.LOW:
        alignment = OutcomeAlignment.UNEXPECTED_REJECTION
        narrative = (
            "Prior classification was LOW, but NACHA return evidence now confirms "
            "rejection. This is an unexpected rejection based on available "
            "historical and syntax evidence."
        )
    elif prior_classification.risk_band == RiskBand.MEDIUM:
        alignment = OutcomeAlignment.RISK_RAISED_BEFORE_REJECTION
        narrative = (
            "Prior classification raised risk before the actual return. NACHA "
            "return evidence now confirms the adverse outcome."
        )
    else:
        alignment = OutcomeAlignment.EXPECTED_REJECTION
        narrative = (
            "Prior classification was HIGH and raised risk before rejection; NACHA "
            "return evidence now confirms the expected adverse outcome."
        )

    return PriorPredictionOutcome(
        prior_risk_score=prior_classification.risk_score,
        prior_risk_band=prior_classification.risk_band,
        prior_clearing_confidence=prior_classification.clearing_confidence,
        actual_outcome_status=payment.current_status.value,
        outcome_alignment=alignment,
        narrative=narrative,
    )


_risk_service_singleton: AIRiskClassificationService | None = None


def get_ai_risk_service() -> AIRiskClassificationService:
    global _risk_service_singleton
    if _risk_service_singleton is None:
        _risk_service_singleton = AIRiskClassificationService.from_env()
    return _risk_service_singleton


def set_ai_risk_service(service: AIRiskClassificationService | None) -> None:
    global _risk_service_singleton
    _risk_service_singleton = service


def reset_ai_risk_service() -> None:
    global _risk_service_singleton
    _risk_service_singleton = None
