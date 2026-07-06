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

_SUCCESS_STATUSES = frozenset({
    "WITH_SCHEME_SUBMITTED",
    "WITH_SCHEME_ACKNOWLEDGED",
    "WITH_BENEFICIARY_BANK_PENDING",
})


def _digits_diff(a: str, b: str) -> int:
    if len(a) != len(b):
        return max(len(a), len(b))
    return sum(x != y for x, y in zip(a, b))


def _build_correction_hints(
    vendor_name: str,
    current_dfi: str,
    current_account_masked: str,
) -> str | None:
    """Compare the current payment's routing/account against past SUCCESSFUL
    payments for the same vendor and return a correction suggestion.

    Scenarios covered:
      1. Same account suffix, same routing → already worked before (reassurance)
      2. Account suffix differs by 1 digit → likely typo, suggest known-good suffix
      3. Routing differs by 1-2 digits  → likely routing typo, suggest known-good routing
      4. Completely different account    → flag mismatch, show what was used successfully
    """
    from payment_tracking_agent.models.payment import PaymentStatus  # noqa: PLC0415

    all_entries = store.list_all_entries()
    vendor_lower = vendor_name.strip().lower()
    current_suffix = current_account_masked[-4:] if len(current_account_masked) >= 4 else current_account_masked

    successful = [
        e for e in all_entries
        if e.individual_name.strip().lower() == vendor_lower
        and e.status.value in _SUCCESS_STATUSES
        and e.dfi_account_number_masked
    ]
    if not successful:
        return None

    # Most common successful account suffix and routing
    from collections import Counter  # noqa: PLC0415
    suffix_counts = Counter(
        e.dfi_account_number_masked[-4:] for e in successful
        if len(e.dfi_account_number_masked) >= 4
    )
    dfi_counts = Counter(e.receiving_dfi for e in successful if e.receiving_dfi)

    best_suffix = suffix_counts.most_common(1)[0][0] if suffix_counts else None
    best_dfi = dfi_counts.most_common(1)[0][0] if dfi_counts else None

    hints: list[str] = []

    # ── Account suffix comparison ─────────────────────────────────────
    if best_suffix:
        if best_suffix == current_suffix:
            hints.append(
                f"account ending ****{current_suffix} was used successfully "
                f"{suffix_counts[best_suffix]}× before — account number looks correct"
            )
        else:
            diff = _digits_diff(best_suffix, current_suffix)
            if diff == 1:
                hints.append(
                    f"POSSIBLE TYPO: current account ****{current_suffix} differs by "
                    f"1 digit from ****{best_suffix} which was used successfully "
                    f"{suffix_counts[best_suffix]}× — did you mean ****{best_suffix}?"
                )
            elif diff <= 2:
                hints.append(
                    f"account ****{current_suffix} not seen in prior successful payments; "
                    f"****{best_suffix} was used successfully {suffix_counts[best_suffix]}× — "
                    "verify account number with beneficiary"
                )
            else:
                hints.append(
                    f"account ****{current_suffix} is completely different from "
                    f"****{best_suffix} used in {suffix_counts[best_suffix]} prior successful "
                    "payments — confirm correct account with beneficiary"
                )

    # ── Routing comparison ────────────────────────────────────────────
    if best_dfi and best_dfi != current_dfi and current_dfi:
        diff = _digits_diff(best_dfi, current_dfi)
        if diff <= 2 and len(best_dfi) == len(current_dfi):
            hints.append(
                f"POSSIBLE TYPO: current routing {current_dfi} differs by {diff} "
                f"digit(s) from {best_dfi} used in {dfi_counts[best_dfi]} prior successful "
                f"payments — did you mean {best_dfi}?"
            )
        else:
            hints.append(
                f"routing {current_dfi} not seen before; prior payments used "
                f"{best_dfi} successfully"
            )

    return " | ".join(hints) if hints else None


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

    # ── Path 2: all other codes — deterministic frequency-based fallback ─
    # Using LLM here is unnecessary: the code description + occurrence count
    # gives operators all the context they need.  Frequency escalation:
    #   3+ occurrences → HIGH (recurring unknown problem)
    #   2  occurrences → MEDIUM
    #   1  occurrence  → LOW (isolated, note only)
    unknown_codes = [
        (code, occs) for code, occs in past_by_code.items()
        if code not in _ACCOUNT_REJECTION_CODES
    ]
    for code, occs in unknown_codes:
        desc = RETURN_REASON_DESCRIPTIONS.get(code, "unknown return reason")
        count = len(occs)
        if count >= 3:
            parts.append(
                f"recurring return {code} ({desc}) × {count} — HIGH frequency, "
                "investigate root cause before resubmission"
            )
        elif count == 2:
            parts.append(
                f"repeated return {code} ({desc}) × {count} — "
                "verify payment details before resubmitting"
            )
        else:
            parts.append(
                f"prior return {code} ({desc}) — review reason before submitting"
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

            # LLM assessment — once per vendor, with fast-path bypasses
            if vendor_key not in customer_ai_cache:
                _action_map = {"HIGH": "HOLD", "MEDIUM": "REVIEW", "LOW": "PROCEED"}

                # ── Fast path 1: HIGH account-rejection history → always HOLD ──
                # The account is definitively invalid; no LLM needed.
                # Include a correction hint from past successful payments.
                if acct_flag and acct_severity == "HIGH":
                    correction = _build_correction_hints(
                        entry.individual_name or vendor_key,
                        entry.receiving_dfi,
                        entry.dfi_account_number_masked,
                    )
                    rec = (
                        f"{acct_flag} Payment withheld — prior account rejection "
                        "indicates high probability of re-rejection."
                    )
                    if correction:
                        rec += f" Correction hint: {correction}."
                    ai_result: dict[str, str] = {"action": "HOLD", "ai_recommendation": rec}

                # ── Fast path 2: LOW risk, no history → always PROCEED ──
                # Clean vendor with no prior issues; LLM would say PROCEED anyway.
                elif risk_level == "LOW" and not acct_flag:
                    ai_result = {
                        "action": "PROCEED",
                        "ai_recommendation": (
                            f"No elevated risk signals detected for {entry.individual_name or vendor_key}. "
                            "Payment cleared for submission."
                        ),
                    }

                # ── Fast path 3: MEDIUM risk, MEDIUM account flag → REVIEW ─
                elif risk_level == "MEDIUM" and acct_flag and acct_severity == "MEDIUM":
                    correction = _build_correction_hints(
                        entry.individual_name or vendor_key,
                        entry.receiving_dfi,
                        entry.dfi_account_number_masked,
                    )
                    rec = f"{acct_flag} Prior return history detected. Review payment details before submitting to scheme."
                    if correction:
                        rec += f" Correction hint: {correction}."
                    ai_result = {"action": "REVIEW", "ai_recommendation": rec}

                # ── Slow path: genuinely ambiguous HIGH risk without account flag ─
                # e.g. high rejection rate with no specific account code — LLM
                # interprets whether the pattern warrants HOLD or REVIEW.
                # Also pass correction hints from past successful payments.
                else:
                    correction = _build_correction_hints(
                        entry.individual_name or vendor_key,
                        entry.receiving_dfi,
                        entry.dfi_account_number_masked,
                    )
                    enriched_reason = risk_reason
                    if correction:
                        enriched_reason = f"{risk_reason} | Past payment comparison: {correction}"
                    try:
                        ai_result = llm_fixer.assess_pre_submission_payment(
                            customer_name=entry.individual_name or vendor_key,
                            customer_id=vendor_key,
                            amount=entry.amount,
                            receiving_dfi=entry.receiving_dfi,
                            account_masked=entry.dfi_account_number_masked,
                            risk_level=risk_level,
                            risk_reason=enriched_reason,
                            historical_total_payments=signals.total_payments,
                            historical_rejections=signals.total_rejections,
                            historical_returns=signals.total_returns,
                            rejection_rate_pct=signals.rejection_rate_pct,
                            rejections_last_30d=signals.rejections_last_30d,
                        )
                        # Enforce minimum action from account flag
                        if acct_flag and acct_severity == "MEDIUM":
                            if ai_result.get("action") == "PROCEED":
                                ai_result = {
                                    "action": "REVIEW",
                                    "ai_recommendation": (
                                        f"{acct_flag} "
                                        f"{ai_result.get('ai_recommendation', '')}".strip()
                                    ),
                                }
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Pre-submission LLM call failed for %s: %s", vendor_key, exc)
                        action = _action_map.get(risk_level, "PROCEED")
                        if acct_flag and acct_severity == "MEDIUM" and action == "PROCEED":
                            action = "REVIEW"
                        ai_result = {
                            "action": action,
                            "ai_recommendation": f"{risk_level} risk — {risk_reason}",
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
