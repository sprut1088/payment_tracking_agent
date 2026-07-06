"""Pre-submission batch risk validation service.

Runs BEFORE payments are pushed to the ACH scheme.  For each payment in a
CCD upload, this service:

1. Retrieves the customer's full historical payment signals from the
   in-memory ledger (rejection rate, return count, recency, velocity).
2. Calls the deterministic risk tier (LOW / MEDIUM / HIGH).
3. Calls the LLM pre-submission assessor to recommend PROCEED / REVIEW / HOLD.
4. Aggregates results to customer and batch level.
5. Returns a ``BatchPreSubmissionResult`` persisted in the ledger store.

The batch is still forwarded to the scheme after validation — the result is
advisory, surfaced to operators via the Batch Dashboard and event log.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from payment_tracking_agent.agents import llm_fixer
from payment_tracking_agent.ledger import store
from payment_tracking_agent.models.payment import UploadRecord
from payment_tracking_agent.models.pre_submission import (
    BatchPreSubmissionResult,
    CustomerRiskSummary,
    PaymentRiskAssessment,
)
from payment_tracking_agent.risk.engine import compute_customer_risk, compute_signals, _customer_key

logger = logging.getLogger(__name__)

# Return codes that specifically indicate an account-number / routing problem
_ACCOUNT_REJECTION_CODES: frozenset[str] = frozenset({
    "R02",  # Account Closed
    "R03",  # No Account / Unable to Locate Account
    "R04",  # Invalid Account Number
    "R16",  # Account Frozen / Access Restricted
    "R20",  # Non-Transaction Account
    "R29",  # Corporate Customer Advises Not Authorized
})


def _check_account_rejection_history(
    customer_key: str,
    receiving_dfi: str,
    account_masked: str,
    customer_name: str = "",
    amount: float = 0.0,
) -> tuple[str | None, str]:
    """Check ALL past return codes for this customer and produce a combined warning.

    Two-path approach:
    - Known account-rejection codes (R03, R04, R16 …) → deterministic message,
      no LLM needed — fast and reliable.
    - Any OTHER return code found in history → passed to the LLM which
      interprets the code, explains its relevance to the current payment,
      and suggests a corrective action.  This covers new or unexpected codes
      without requiring a code change.

    Returns a tuple of ``(warning_text, severity)`` where *severity* is
    ``"HIGH"`` (account-level codes — likely permanent) or ``"MEDIUM"``
    (other codes — review recommended).  Returns ``(None, "LOW")`` when no
    history is found.
    """
    from payment_tracking_agent.models.return_file import RETURN_REASON_DESCRIPTIONS  # noqa: PLC0415

    all_entries = store.list_all_entries()
    current_suffix = account_masked[-4:] if len(account_masked) >= 4 else account_masked

    # Match by vendor name (individual_name) — the beneficiary who was previously
    # rejected.  Using company key here would miss old ledger entries that were
    # parsed before company_identification was added to EntryDetailRecord.
    vendor_key = customer_name.strip().lower() if customer_name else customer_key.strip().lower()

    # Collect ALL past return codes for this vendor
    past_by_code: dict[str, list] = {}
    for entry in all_entries:
        if entry.individual_name.strip().lower() != vendor_key:
            continue
        if not entry.return_reason_code:
            continue
        past_by_code.setdefault(entry.return_reason_code, []).append(entry)

    if not past_by_code:
        return None, "LOW"

    parts: list[str] = []

    # ── Path 1: known account-rejection codes — deterministic ────────────
    for code, occurrences in past_by_code.items():
        if code not in _ACCOUNT_REJECTION_CODES:
            continue
        past_suffix = occurrences[-1].dfi_account_number_masked[-4:] if len(
            occurrences[-1].dfi_account_number_masked) >= 4 else ""
        desc = RETURN_REASON_DESCRIPTIONS.get(code, "account error")
        if past_suffix == current_suffix:
            parts.append(
                f"account ending {current_suffix} was rejected {len(occurrences)}× "
                f"({code} — {desc})"
            )
        elif occurrences[-1].receiving_dfi == receiving_dfi and receiving_dfi:
            parts.append(
                f"routing {receiving_dfi} appeared in a prior {code} return ({desc})"
            )

    # ── Path 2: all other codes — ask LLM to interpret ───────────────────
    unknown_codes = [
        (code, occs) for code, occs in past_by_code.items()
        if code not in _ACCOUNT_REJECTION_CODES
    ]
    if unknown_codes:
        try:
            # Build a compact summary of the unknown codes for the LLM
            code_lines = "\n".join(
                f"  {code} ({RETURN_REASON_DESCRIPTIONS.get(code, 'unknown')}) "
                f"× {len(occs)} time(s)"
                for code, occs in unknown_codes
            )
            user_msg = (
                f"Customer: {customer_name or customer_key}\n"
                f"Current payment: routing {receiving_dfi}, account ending {current_suffix}, "
                f"amount ${amount:.2f}\n\n"
                f"Historical return codes for this customer NOT in known account-rejection set:\n"
                f"{code_lines}\n\n"
                "For each code: explain whether it poses a risk for the current payment, "
                "and suggest a specific corrective action the bank operator should take "
                "before submitting to scheme.\n"
                "Respond with a single concise paragraph (2-3 sentences)."
            )
            llm_analysis = llm_fixer._call_generic_llm(  # noqa: SLF001
                system=(
                    "You are an ACH payment risk analyst. "
                    "Analyse historical return codes for a customer and advise whether "
                    "they indicate risk for a new payment. Be specific and actionable. "
                    "Do NOT invent data beyond what is provided."
                ),
                user=user_msg,
                max_tokens=300,
            )
            if llm_analysis:
                parts.append(f"LLM analysis of other past codes: {llm_analysis}")
        except Exception as exc:  # noqa: BLE001
            logger.debug("LLM analysis of unknown return codes skipped: %s", exc)
            # Deterministic fallback for unknown codes
            for code, occs in unknown_codes:
                desc = RETURN_REASON_DESCRIPTIONS.get(code, "unknown return")
                parts.append(
                    f"past return {code} ({desc}) × {len(occs)} — "
                    "review reason before submitting"
                )

    if not parts:
        return None, "LOW"

    # Determine severity of the combined flag:
    # Any known account-rejection code (R03/R04/R16…) → HIGH (account may be invalid)
    # Unknown/other codes only                         → MEDIUM (needs review)
    has_account_code = any(
        code in _ACCOUNT_REJECTION_CODES for code in past_by_code
    )
    flag_severity = "HIGH" if has_account_code else "MEDIUM"

    seen: set[str] = set()
    unique = [p for p in parts if not (p in seen or seen.add(p))]  # type: ignore[func-returns-value]
    return "HISTORY FLAG: " + "; ".join(unique[:4]) + ".", flag_severity

_RISK_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_ACTION_ORDER = {"HOLD": 0, "REVIEW": 1, "PROCEED": 2}


def _worst_risk(*levels: str) -> str:
    return min(levels, key=lambda l: _RISK_ORDER.get(l, 9))


def _worst_action(*actions: str) -> str:
    return min(actions, key=lambda a: _ACTION_ORDER.get(a, 9))


def validate_batch_before_submission(upload_record: UploadRecord) -> BatchPreSubmissionResult:
    """Run full pre-submission risk validation for one CCD upload.

    Computes per-payment and per-customer risk assessments using the in-memory
    ledger history, then calls the LLM assessor for each unique customer.

    Results are deterministic when no LLM key is configured.

    Args:
        upload_record: The fully parsed CCD upload to validate.

    Returns:
        ``BatchPreSubmissionResult`` ready to be stored and surfaced via the API.
    """
    history = store.list_all_entries_with_timestamps()

    # ── Per-payment assessments ───────────────────────────────────────────
    payment_assessments: list[PaymentRiskAssessment] = []

    # All caches are keyed by VENDOR (individual_name) not by company.
    # Using the company key would collapse all 20 vendors onto one cached result,
    # preventing per-vendor HOLD decisions and inflating risk via the feedback loop
    # caused by WITH_BANK_VALIDATION_FAILED counting as a rejection.
    customer_ai_cache: dict[str, dict[str, str]] = {}
    risk_cache: dict[str, tuple[str, str]] = {}
    signals_cache: dict[str, object] = {}

    for batch in upload_record.parsed.batches:
        for entry in batch.entries:
            cid = _customer_key(entry)
            # Per-vendor key for risk/AI caches — each vendor assessed individually.
            vendor_key = (entry.individual_name.strip() or entry.individual_id_number.strip()
                          or entry.trace_number)

            # Risk engine (deterministic) — per vendor
            if vendor_key not in risk_cache:
                risk_level, risk_reason = compute_customer_risk(vendor_key, history)
                risk_cache[vendor_key] = (risk_level, risk_reason)
            risk_level, risk_reason = risk_cache[vendor_key]

            # ── Account/vendor rejection history check ────────────────────
            acct_flag, acct_severity = _check_account_rejection_history(
                customer_key=vendor_key,
                receiving_dfi=entry.receiving_dfi,
                account_masked=entry.dfi_account_number_masked,
                customer_name=entry.individual_name or vendor_key,
                amount=entry.amount,
            )
            if acct_flag:
                risk_level = _worst_risk(risk_level, acct_severity)
                risk_reason = f"{acct_flag} {risk_reason}".strip()
                logger.info(
                    "Pre-submission account flag [%s] — vendor=%s trace=%s: %s",
                    acct_severity, vendor_key, entry.trace_number, acct_flag,
                )

            # Signals (for LLM prompt) — per vendor
            if vendor_key not in signals_cache:
                signals_cache[vendor_key] = compute_signals(vendor_key, history)
            signals = signals_cache[vendor_key]  # type: ignore[assignment]

            # LLM assessment — once per vendor
            if vendor_key not in customer_ai_cache:
                try:
                    ai_result = llm_fixer.assess_pre_submission_payment(
                        customer_name=entry.individual_name or vendor_key,
                        customer_id=vendor_key,
                        amount=entry.amount,
                        receiving_dfi=entry.receiving_dfi,
                        account_masked=entry.dfi_account_number_masked,
                        risk_level=risk_level,
                        risk_reason=risk_reason,
                        historical_total_payments=signals.total_payments,
                        historical_rejections=signals.total_rejections,
                        historical_returns=signals.total_returns,
                        rejection_rate_pct=signals.rejection_rate_pct,
                        rejections_last_30d=signals.rejections_last_30d,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Pre-submission LLM call failed for %s: %s", vendor_key, exc)
                    _action_map = {"HIGH": "HOLD", "MEDIUM": "REVIEW", "LOW": "PROCEED"}
                    ai_result = {
                        "action": _action_map.get(risk_level, "PROCEED"),
                        "ai_recommendation": f"{risk_level} risk — {risk_reason}",
                    }
                if acct_flag:
                    current_action = ai_result.get("action", "PROCEED")
                    if acct_severity == "HIGH" and current_action != "HOLD":
                        ai_result = {
                            "action": "HOLD",
                            "ai_recommendation": (
                                f"{acct_flag} "
                                f"{ai_result.get('ai_recommendation', '')}".strip()
                            ),
                        }
                    elif acct_severity == "MEDIUM" and current_action == "PROCEED":
                        ai_result = {
                            "action": "REVIEW",
                            "ai_recommendation": (
                                f"{acct_flag} "
                                f"{ai_result.get('ai_recommendation', '')}".strip()
                            ),
                        }
                customer_ai_cache[vendor_key] = ai_result

            ai = customer_ai_cache[vendor_key]

            payment_assessments.append(PaymentRiskAssessment(
                trace_number=entry.trace_number,
                customer_id=cid,
                customer_name=entry.individual_name or cid,
                amount=entry.amount,
                receiving_dfi=entry.receiving_dfi,
                account_masked=entry.dfi_account_number_masked,
                risk_level=risk_level,
                risk_reason=risk_reason,
                historical_total_payments=signals.total_payments,
                historical_rejections=signals.total_rejections,
                historical_returns=signals.total_returns,
                rejection_rate_pct=signals.rejection_rate_pct,
                rejections_last_30d=signals.rejections_last_30d,
                action=ai["action"],
                ai_recommendation=ai["ai_recommendation"],
            ))

    # ── Customer summaries ────────────────────────────────────────────────
    by_customer: dict[str, list[PaymentRiskAssessment]] = {}
    for pa in payment_assessments:
        by_customer.setdefault(pa.customer_id, []).append(pa)

    customer_summaries: list[CustomerRiskSummary] = []
    for cid, pas in by_customer.items():
        worst_risk = _worst_risk(*(p.risk_level for p in pas))
        worst_action = _worst_action(*(p.action for p in pas))
        worst_pa = next(
            p for p in pas
            if p.risk_level == worst_risk and p.action == worst_action
        )
        customer_summaries.append(CustomerRiskSummary(
            customer_id=cid,
            customer_name=pas[0].customer_name,
            payment_count=len(pas),
            total_amount=sum(p.amount for p in pas),
            risk_level=worst_risk,
            risk_reason=worst_pa.risk_reason,
            action=worst_action,
            ai_recommendation=worst_pa.ai_recommendation,
            trace_numbers=[p.trace_number for p in pas],
        ))

    # Sort: worst risk first
    customer_summaries.sort(
        key=lambda c: (_RISK_ORDER.get(c.risk_level, 9), _ACTION_ORDER.get(c.action, 9))
    )

    # ── Batch aggregation ─────────────────────────────────────────────────
    total = len(payment_assessments)
    high_count = sum(1 for p in payment_assessments if p.risk_level == "HIGH")
    medium_count = sum(1 for p in payment_assessments if p.risk_level == "MEDIUM")
    low_count = sum(1 for p in payment_assessments if p.risk_level == "LOW")
    hold_count = sum(1 for p in payment_assessments if p.action == "HOLD")
    review_count = sum(1 for p in payment_assessments if p.action == "REVIEW")
    proceed_count = sum(1 for p in payment_assessments if p.action == "PROCEED")

    batch_risk = "HIGH" if high_count else ("MEDIUM" if medium_count else "LOW")

    if hold_count:
        batch_risk_reason = (
            f"{hold_count} payment(s) flagged HOLD — high risk of rejection or return. "
            "Review before scheme submission."
        )
    elif review_count:
        batch_risk_reason = (
            f"{review_count} payment(s) flagged REVIEW — medium risk signals detected."
        )
    else:
        batch_risk_reason = f"All {total} payment(s) assessed as PROCEED — no elevated risk signals."

    # AI batch summary (based on worst customers)
    hold_customers = [c for c in customer_summaries if c.action == "HOLD"]
    if hold_customers:
        ai_batch_summary = (
            f"Batch contains {hold_count} HOLD recommendation(s). "
            f"High-risk customers: {', '.join(c.customer_name for c in hold_customers[:3])}. "
            "Review flagged payments before submitting to scheme."
        )
    elif review_count:
        review_customers = [c for c in customer_summaries if c.action == "REVIEW"]
        ai_batch_summary = (
            f"Batch contains {review_count} REVIEW recommendation(s). "
            f"Monitor: {', '.join(c.customer_name for c in review_customers[:3])}. "
            "Submit with caution and monitor for returns."
        )
    else:
        ai_batch_summary = (
            f"All {total} payment(s) cleared for submission. "
            "No elevated risk signals detected in customer history."
        )

    result = BatchPreSubmissionResult(
        upload_id=upload_record.upload_id,
        file_name=upload_record.file_name,
        validated_at=datetime.now(tz=timezone.utc),
        batch_risk_level=batch_risk,
        batch_risk_reason=batch_risk_reason,
        total_payments=total,
        high_risk_count=high_count,
        medium_risk_count=medium_count,
        low_risk_count=low_count,
        hold_count=hold_count,
        review_count=review_count,
        proceed_count=proceed_count,
        payment_assessments=payment_assessments,
        customer_summaries=customer_summaries,
        ai_batch_summary=ai_batch_summary,
    )

    logger.info(
        "Pre-submission validation — %s: total=%d high=%d medium=%d low=%d "
        "hold=%d review=%d proceed=%d",
        upload_record.file_name,
        total, high_count, medium_count, low_count,
        hold_count, review_count, proceed_count,
    )
    return result
