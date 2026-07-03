"""Customer-level risk engine.

Risk is computed per *customer* (``individual_id_number``) using time-aware
signals extracted from their full payment history:

Signals
-------
1. **Overall rejection rate** — rejected payments / total payments.
2. **Beneficiary-bank return count** — NACHA return file matches.
3. **Recency** — rejections in the last 30 / 90 days.
4. **Inter-rejection gaps** — days between consecutive rejection events;
   tightly-clustered rejections are a stronger signal than spread-out ones.
5. **Velocity** — rejection events per 30-day rolling window.

Deterministic tiers (fallback when LLM is unavailable)
-------------------------------------------------------
| Tier   | Rate threshold | Return threshold | Recency / velocity override |
|--------|---------------|------------------|-----------------------------|
| HIGH   | ≥ 50 %        | ≥ 2 returns      | ≥ 2 rejections in 30 days   |
| MEDIUM | ≥ 20 %        | ≥ 1 return       | ≥ 1 rejection in 30 days    |
| LOW    | < 20 %        | 0 returns        | —                           |

Either condition within a tier triggers it.

LLM assessment
--------------
When an LLM API key is configured (same ``settings`` as ``llm_fixer``), the
engine serialises the signals into a compact JSON prompt and asks the LLM to
return ``{ "risk_level": "LOW"|"MEDIUM"|"HIGH", "risk_reason": "…" }``.
The deterministic tier is used as a baseline hint so the LLM cannot wildly
contradict the hard rules.  On any LLM failure the deterministic result is
used transparently.

Usage
-----
    from payment_tracking_agent.risk.engine import compute_customer_risk
    from payment_tracking_agent.ledger import store

    history = store.list_all_entries_with_timestamps()
    risk_level, risk_reason = compute_customer_risk(customer_id, history)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from payment_tracking_agent.models.payment import EntryDetailRecord, PaymentStatus

logger = logging.getLogger(__name__)

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]

# ── statuses that count as a rejection (any source) ──────────────────────────
_REJECTED_STATUSES: frozenset[PaymentStatus] = frozenset(
    {
        PaymentStatus.REJECTED_BY_RETURN_FILE,     # beneficiary-bank return
        PaymentStatus.REJECTED_BY_SETTLEMENT,       # settlement rejection
        PaymentStatus.WITH_BANK_VALIDATION_FAILED,  # failed bank-side validation
    }
)

_RETURN_FILE_STATUSES: frozenset[PaymentStatus] = frozenset(
    {PaymentStatus.REJECTED_BY_RETURN_FILE}
)


# ---------------------------------------------------------------------------
# Signals dataclass
# ---------------------------------------------------------------------------

@dataclass
class CustomerRiskSignals:
    """All time-aware signals computed for a single customer."""

    customer_id: str
    total_payments: int
    total_rejections: int
    total_returns: int                  # beneficiary-bank returns specifically
    rejection_rate_pct: float           # 0–100
    rejections_last_30d: int
    rejections_last_90d: int
    inter_rejection_gaps_days: list[float] = field(default_factory=list)

    @property
    def min_gap_days(self) -> float | None:
        return min(self.inter_rejection_gaps_days) if self.inter_rejection_gaps_days else None

    @property
    def max_gap_days(self) -> float | None:
        return max(self.inter_rejection_gaps_days) if self.inter_rejection_gaps_days else None

    @property
    def avg_gap_days(self) -> float | None:
        g = self.inter_rejection_gaps_days
        return sum(g) / len(g) if g else None

    def to_prompt_dict(self) -> dict:
        """Compact dict passed to the LLM prompt."""
        return {
            "customer_id": self.customer_id,
            "total_payments": self.total_payments,
            "total_rejections": self.total_rejections,
            "total_beneficiary_bank_returns": self.total_returns,
            "rejection_rate_pct": round(self.rejection_rate_pct, 1),
            "rejections_last_30_days": self.rejections_last_30d,
            "rejections_last_90_days": self.rejections_last_90d,
            "inter_rejection_gap_days": {
                "min": round(self.min_gap_days, 1) if self.min_gap_days is not None else None,
                "max": round(self.max_gap_days, 1) if self.max_gap_days is not None else None,
                "avg": round(self.avg_gap_days, 1) if self.avg_gap_days is not None else None,
                "count": len(self.inter_rejection_gaps_days),
            },
        }


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def _compute_signals(
    customer_id: str,
    history: list[tuple[EntryDetailRecord, datetime]],
) -> CustomerRiskSignals:
    """Extract all risk signals for *customer_id* from the ledger history."""
    now = datetime.now(tz=timezone.utc)
    cutoff_30d = now.replace(tzinfo=timezone.utc) if now.tzinfo else now
    # make cutoff timezone-aware regardless of input
    from datetime import timedelta
    cutoff_30d = now - timedelta(days=30)
    cutoff_90d = now - timedelta(days=90)

    customer_history = [
        (entry, ts) for entry, ts in history
        if entry.individual_id_number == customer_id
    ]
    total = len(customer_history)

    if total == 0:
        return CustomerRiskSignals(
            customer_id=customer_id,
            total_payments=0,
            total_rejections=0,
            total_returns=0,
            rejection_rate_pct=0.0,
            rejections_last_30d=0,
            rejections_last_90d=0,
        )

    # Normalise timestamps to UTC-aware
    def _utc(ts: datetime) -> datetime:
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts

    rejected_events: list[datetime] = sorted(
        _utc(ts)
        for entry, ts in customer_history
        if entry.status in _REJECTED_STATUSES
    )
    total_rejections = len(rejected_events)
    total_returns = sum(
        1 for entry, _ in customer_history if entry.status in _RETURN_FILE_STATUSES
    )
    rejection_rate = total_rejections / total if total > 0 else 0.0

    rejections_last_30d = sum(1 for ts in rejected_events if ts >= cutoff_30d)
    rejections_last_90d = sum(1 for ts in rejected_events if ts >= cutoff_90d)

    # Inter-rejection gaps (days between consecutive events, sorted chronologically)
    gaps: list[float] = []
    for i in range(1, len(rejected_events)):
        delta = (rejected_events[i] - rejected_events[i - 1]).total_seconds() / 86400
        gaps.append(round(delta, 2))

    return CustomerRiskSignals(
        customer_id=customer_id,
        total_payments=total,
        total_rejections=total_rejections,
        total_returns=total_returns,
        rejection_rate_pct=round(rejection_rate * 100, 1),
        rejections_last_30d=rejections_last_30d,
        rejections_last_90d=rejections_last_90d,
        inter_rejection_gaps_days=gaps,
    )


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------

def _deterministic_level(signals: CustomerRiskSignals) -> tuple[RiskLevel, str]:
    """Return (level, reason) using hard threshold rules — no LLM required."""
    rate = signals.rejection_rate_pct
    returns = signals.total_returns
    rejected = signals.total_rejections
    total = signals.total_payments
    last_30d = signals.rejections_last_30d

    if total == 0:
        return "LOW", "No payment history available for this customer."

    if rate >= 50 or returns >= 2 or last_30d >= 2:
        parts: list[str] = [f"Rejection rate {rate:.0f}% ({rejected}/{total} payments)."]
        if returns >= 2:
            parts.append(f"{returns} beneficiary-bank returns on record.")
        if last_30d >= 2:
            parts.append(f"{last_30d} rejections in the last 30 days.")
        return "HIGH", " ".join(parts)

    if rate >= 20 or returns >= 1 or last_30d >= 1:
        parts = [f"Rejection rate {rate:.0f}% ({rejected}/{total} payments)."]
        if returns >= 1:
            parts.append(f"{returns} beneficiary-bank return{'s' if returns > 1 else ''} on record.")
        if last_30d >= 1:
            parts.append("Recent rejection activity in the last 30 days.")
        return "MEDIUM", " ".join(parts)

    if total == 1 and rejected == 0:
        return "LOW", "Single payment with no rejection history."

    return "LOW", (
        f"Rejection rate {rate:.0f}% ({rejected}/{total} payments). "
        "No elevated risk signals."
    )


# ---------------------------------------------------------------------------
# LLM assessment
# ---------------------------------------------------------------------------

_LLM_SYSTEM = """\
You are an ACH payment risk analyst for a bank operations team.
You will be given computed signals about a customer's payment history.
Assess the customer's risk level as LOW, MEDIUM, or HIGH.

Risk tier guidelines (use as a baseline — adjust for recency and clustering):
- HIGH  : rejection rate ≥ 50%, OR ≥ 2 beneficiary-bank returns,
          OR ≥ 2 rejections in the last 30 days (high velocity / clustering).
- MEDIUM: rejection rate ≥ 20%, OR ≥ 1 beneficiary-bank return,
          OR ≥ 1 rejection in the last 30 days.
- LOW   : rejection rate < 20%, no beneficiary-bank returns, no recent rejections.

Also consider:
- Short inter-rejection gaps (< 7 days) indicate clustered / recurring failures → lean higher.
- All rejections older than 90 days with no recent activity → can lean lower.
- A single isolated rejection with no recurrence → MEDIUM at most.

Respond with a JSON object only — no markdown, no prose:
{
  "risk_level": "LOW" | "MEDIUM" | "HIGH",
  "risk_reason": "<1-2 sentences citing the most important signals>"
}
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```\s*$", "", text)
    return text.strip()


def _call_llm(signals: CustomerRiskSignals, baseline: RiskLevel) -> tuple[RiskLevel, str] | None:
    """Call the configured LLM provider and return (level, reason), or None on failure."""
    try:
        from payment_tracking_agent.config import settings  # noqa: PLC0415
    except Exception:
        return None

    _env_anthropic = (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("PTA_ANTHROPIC_API_KEY")
    )

    if not settings.llm_api_key and not settings.anthropic_api_key and not _env_anthropic:
        logger.debug("Risk engine: no LLM key — using deterministic result.")
        return None

    provider = (settings.llm_provider or "openai").lower()
    model = settings.llm_model
    max_tok = min(settings.llm_max_tokens, 300)  # risk reason is short

    if provider == "anthropic":
        api_key = settings.anthropic_api_key or settings.llm_api_key or _env_anthropic
    else:
        api_key = settings.llm_api_key or settings.anthropic_api_key or _env_anthropic

    if not api_key:
        return None

    user_message = (
        f"Deterministic baseline tier: {baseline}\n\n"
        f"Customer payment history signals:\n"
        f"{json.dumps(signals.to_prompt_dict(), indent=2)}\n\n"
        "Return a JSON object only."
    )

    try:
        raw_text = ""
        if provider == "anthropic":
            from anthropic import Anthropic  # noqa: PLC0415
            client = Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=max_tok,
                system=_LLM_SYSTEM,
                messages=[{"role": "user", "content": user_message}],
            )
            raw_text = response.content[0].text if response.content else ""
        else:
            from openai import OpenAI  # noqa: PLC0415
            client = OpenAI(api_key=api_key, base_url=settings.llm_base_url or None)
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tok,
                messages=[
                    {"role": "system", "content": _LLM_SYSTEM},
                    {"role": "user", "content": user_message},
                ],
            )
            raw_text = (response.choices[0].message.content or "") if response.choices else ""

        parsed = json.loads(_strip_fences(raw_text))
        level_raw = str(parsed.get("risk_level", "")).upper()
        reason = str(parsed.get("risk_reason", "")).strip()
        if level_raw not in ("LOW", "MEDIUM", "HIGH") or not reason:
            logger.warning("Risk LLM returned unexpected payload: %s", raw_text[:200])
            return None
        return level_raw, reason  # type: ignore[return-value]

    except Exception as exc:  # noqa: BLE001
        logger.warning("Risk LLM call failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Module-level risk cache — shared across all HTTP requests
# ---------------------------------------------------------------------------
# Key: customer_id  Value: (risk_level, risk_reason, monotonic_timestamp)
_RISK_CACHE: dict[str, tuple[str, str, float]] = {}
_RISK_CACHE_TTL_S: float = 60.0  # recompute after 60 seconds


def invalidate_risk_cache() -> None:
    """Clear the risk cache (called on store.clear() in tests)."""
    _RISK_CACHE.clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_customer_risk(
    customer_id: str,
    history: list[tuple[EntryDetailRecord, datetime]],
) -> tuple[RiskLevel, str]:
    """Compute risk for *customer_id* using time-aware signals + optional LLM.

    Parameters
    ----------
    customer_id:
        The ``individual_id_number`` value for the customer.
    history:
        List of ``(EntryDetailRecord, uploaded_at)`` tuples for **all**
        customers (the engine filters to the relevant customer internally).
        Obtain from ``store.list_all_entries_with_timestamps()``.

    Returns
    -------
    ``(risk_level, risk_reason)``
    """
    cached = _RISK_CACHE.get(customer_id)
    if cached and (time.monotonic() - cached[2]) < _RISK_CACHE_TTL_S:
        return cached[0], cached[1]  # type: ignore[return-value]

    signals = _compute_signals(customer_id, history)
    baseline_level, baseline_reason = _deterministic_level(signals)

    # Fast-path: skip the LLM when there is nothing meaningful to analyse.
    # Single-payment customers and customers with no rejections or returns are
    # always LOW — calling the LLM for every one wastes ~1-5 s per customer.
    if signals.total_payments <= 1 or (signals.total_rejections == 0 and signals.total_returns == 0):
        _RISK_CACHE[customer_id] = (baseline_level, baseline_reason, time.monotonic())
        return baseline_level, baseline_reason

    llm_result = _call_llm(signals, baseline_level)
    level, reason = llm_result if llm_result is not None else (baseline_level, baseline_reason)
    _RISK_CACHE[customer_id] = (level, reason, time.monotonic())
    return level, reason
