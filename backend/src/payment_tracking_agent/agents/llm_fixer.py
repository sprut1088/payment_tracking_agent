"""LLM-powered fix suggestions for invalid ACH CCD file lines.

Takes the errored lines detected by the CCD validator and sends them to the
configured LLM in a single batched call.  The LLM is asked to return a JSON
array of corrections — one element per errored line.

If no LLM API key is configured the function returns an empty list so the
caller can still surface validation errors without crashing.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING

from payment_tracking_agent.config import settings

if TYPE_CHECKING:
    from payment_tracking_agent.validators.ccd_validator import LineError

logger = logging.getLogger(__name__)


def _strip_code_fences(text: str) -> str:
    """Remove markdown ```json ... ``` wrappers that some models add despite instructions."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text)
    return text.strip()


def _call_generic_llm(system: str, user: str, max_tokens: int = 300) -> str | None:
    """Send a free-form system+user prompt to the configured LLM.

    Used by services that need ad-hoc analysis (e.g. unknown return codes)
    without a structured JSON schema.  Returns the raw text response, or
    ``None`` when no LLM key is configured or the call fails.
    """
    _env_anthropic = (
        os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("PTA_ANTHROPIC_API_KEY")
    )
    api_key = settings.llm_api_key or settings.anthropic_api_key or _env_anthropic
    if not api_key:
        return None
    provider = (settings.llm_provider or "openai").lower()
    model = settings.llm_model
    try:
        if provider == "anthropic":
            from anthropic import Anthropic  # noqa: PLC0415
            client = Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text.strip() if response.content else None
        else:
            from openai import OpenAI  # noqa: PLC0415
            client = OpenAI(api_key=api_key, base_url=settings.llm_base_url or None)
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return (response.choices[0].message.content or "").strip() or None
    except Exception as exc:  # noqa: BLE001
        logger.debug("_call_generic_llm failed: %s", exc)
        return None


def _salvage_truncated_array(text: str) -> str:
    """Close a JSON array that was cut off mid-stream (max_tokens hit)."""
    last_brace = text.rfind('}')
    if last_brace == -1:
        return '[]'
    return text[: last_brace + 1] + ']'


_SYSTEM_PROMPT = """\
You are an expert in the NACHA ACH fixed-width file format.
Every record must be EXACTLY 94 characters wide.

CRITICAL: Lines may have INTERNAL FIELD MISALIGNMENT — not just missing trailing spaces.
You must RECONSTRUCT each record from its field values using the exact positions below.
Do NOT simply pad or trim the end. Extract each field value from the raw line by its
approximate content, then place it at the correct position.

EXACT FIELD POSITIONS (0-based Python slice notation):

TYPE 1 — File Header (total 94 chars):
  [0]      Record Type Code              = '1'
  [1:3]    Priority Code                 = '01'
  [3:13]   Immediate Destination         10 chars  (space + 9-digit routing)
  [13:23]  Immediate Origin              10 chars  (space + 9-digit origin)
  [23:29]  File Creation Date            6 chars   YYMMDD
  [29:33]  File Creation Time            4 chars   HHMM
  [33]     File ID Modifier              1 char
  [34:37]  Record Size                   = '094'
  [37:39]  Blocking Factor               = '10'
  [39]     Format Code                   = '1'
  [40:63]  Immediate Destination Name    23 chars  left-justified, space-padded
  [63:86]  Immediate Origin Name         23 chars  left-justified, space-padded
  [86:94]  Reference Code                8 chars   spaces if unused

TYPE 5 — Batch Header (total 94 chars):
  [0]      Record Type Code              = '5'
  [1:4]    Service Class Code            3 chars   (200/220/225)
  [4:20]   Company Name                  16 chars  left-justified, space-padded
  [20:40]  Company Discretionary Data    20 chars  spaces if unused
  [40:50]  Company Identification        10 chars
  [50:53]  Standard Entry Class Code     3 chars   e.g. 'CCD'
  [53:63]  Company Entry Description     10 chars  left-justified, space-padded
  [63:69]  Company Descriptive Date      6 chars   YYMMDD or spaces
  [69:75]  Effective Entry Date          6 chars   YYMMDD
  [75:78]  Settlement Date               3 chars   spaces (bank-filled)
  [78]     Originator Status Code        1 char
  [79:87]  ODFI Identification           8 chars
  [87:94]  Batch Number                  7 chars   zero-padded

TYPE 6 — Entry Detail / CCD (total 94 chars):
  [0]      Record Type Code              = '6'
  [1:3]    Transaction Code              2 chars   (22=checking credit, 27=debit…)
  [3:11]   RDFI Routing Transit Number   8 chars   first 8 digits of 9-digit routing
  [11]     Check Digit                   1 digit
  [12:29]  DFI Account Number            17 chars  LEFT-JUSTIFIED, space-padded RIGHT
  [29:39]  Amount                        10 chars  zero-padded cents, no decimal point
  [39:54]  Individual Identification No  15 chars  left-justified, space-padded
  [54:76]  Individual Name               22 chars  left-justified, space-padded
  [76]     Addenda Record Indicator      1 char    '0' = no addenda
  [77:94]  Trace Number                  17 chars  8-digit ODFI + 9-digit sequence

TYPE 8 — Batch Control (total 94 chars):
  [0]      Record Type Code              = '8'
  [1:4]    Service Class Code            3 chars
  [4:10]   Entry/Addenda Count           6 chars   zero-padded
  [10:20]  Entry Hash                    10 chars  sum of all RDFI routings mod 10^10
  [20:32]  Total Debit Dollar Amount     12 chars  zero-padded cents
  [32:44]  Total Credit Dollar Amount    12 chars  zero-padded cents
  [44:54]  Company Identification        10 chars
  [54:73]  Message Authentication Code   19 chars  spaces
  [73:79]  Reserved                      6 chars   spaces
  [79:87]  ODFI Identification           8 chars
  [87:94]  Batch Number                  7 chars

TYPE 9 — File Control (total 94 chars):
  [0]      Record Type Code              = '9'
  [1:7]    Batch Count                   6 chars   zero-padded
  [7:13]   Block Count                   6 chars   zero-padded
  [13:21]  Entry/Addenda Count           8 chars   zero-padded
  [21:31]  Entry Hash                    10 chars
  [31:43]  Total Debit Dollar Amount     12 chars
  [43:55]  Total Credit Dollar Amount    12 chars
  [55:94]  Reserved                      39 chars  spaces

RECONSTRUCTION RULES:
1. Identify the record type from character [0].
2. Extract each field VALUE from the raw line by its approximate location or visible content.
3. Place each field value at its EXACT correct slice position listed above.
4. Pad or truncate each field to exactly its required width.
5. The assembled record MUST be exactly 94 characters — verify by counting.
6. For TYPE 6 specifically:
   - DFI Account Number [12:29]: left-justify the account digits, pad right with spaces to 17.
   - Amount [29:39]: zero-padded 10-digit integer (cents). Extract the numeric value visible
     in the raw line (e.g. "0000010000" = $100.00).
   - Trace Number [77:94]: 8-digit ODFI routing (no check digit) + 9-digit sequence, total 17.

Respond with a JSON array only — no markdown, no prose.
Each element must contain exactly:
  {
    "line_number": <int>,
    "corrected_line": "<string, exactly 94 chars>",
    "explanation": "<brief plain-English description of what was fixed>"
  }
"""


def suggest_fixes(
    errored_lines: list[tuple[int, str, list["LineError"]]],
) -> list[dict]:
    """Request LLM corrections for every errored line.

    Args:
        errored_lines: List of ``(line_number, raw_line, errors)`` tuples
                       produced by ``validate_lines``.

    Returns:
        List of dicts with keys ``line_number``, ``original_line``,
        ``corrected_line``, and ``explanation``.
        Returns an empty list when the LLM is unavailable or the call fails.
    """
    if not errored_lines:
        return []

    # Fall back to os.environ directly in case pydantic-settings env_prefix
    # prevented the non-prefixed key from being read from the .env file.
    _env_anthropic = (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("PTA_ANTHROPIC_API_KEY")
    )

    if not settings.llm_api_key and not settings.anthropic_api_key and not _env_anthropic:
        logger.warning("No LLM API key configured — skipping LLM fix suggestions.")
        return []

    provider = (settings.llm_provider or "openai").lower()
    model = settings.llm_model
    max_tok = settings.llm_max_tokens

    if provider == "anthropic":
        api_key = settings.anthropic_api_key or settings.llm_api_key or _env_anthropic
    else:
        api_key = settings.llm_api_key or settings.anthropic_api_key or _env_anthropic

    if not api_key:
        logger.warning("No API key found for provider '%s' — skipping.", provider)
        return []

    logger.info("LLM fixer: provider=%s model=%s max_tokens=%d", provider, model, max_tok)

    # Build the user message — group all errored lines into one request
    lines_block = "\n\n".join(
        "Line {ln} (record type '{rtype}'):\n"
        "  Raw  : {raw!r}\n"
        "  Errors: {errs}".format(
            ln=ln,
            rtype=raw[0:1],
            raw=raw,
            errs="; ".join(e.issue for e in errs),
        )
        for ln, raw, errs in errored_lines
    )
    user_message = f"Fix the following ACH CCD file lines:\n\n{lines_block}\n\nReturn a JSON array only."

    raw_text = ""
    try:
        if provider == "anthropic":
            try:
                from anthropic import Anthropic  # noqa: PLC0415
            except ImportError:
                logger.error("anthropic package not installed — skipping LLM fix suggestions.")
                return []
            client = Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=max_tok,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw_text = response.content[0].text if response.content else ""
        else:
            try:
                from openai import OpenAI  # noqa: PLC0415
            except ImportError:
                logger.error("openai package not installed — skipping LLM fix suggestions.")
                return []
            client = OpenAI(
                api_key=api_key,
                base_url=settings.llm_base_url or None,
            )
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tok,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
            raw_text = response.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM request failed: %s", exc, exc_info=True)
        return []

    raw_text = _strip_code_fences(raw_text)

    try:
        suggestions = json.loads(raw_text)
    except json.JSONDecodeError:
        salvaged = _salvage_truncated_array(raw_text)
        try:
            suggestions = json.loads(salvaged)
            logger.warning("LLM response was truncated — salvaged %d suggestions.", len(suggestions))
        except json.JSONDecodeError:
            logger.error("Could not parse LLM response as JSON: %r", raw_text[:200])
            return []

    result = []
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        ln = item.get("line_number")
        corrected = item.get("corrected_line", "")
        explanation = item.get("explanation", "")
        if ln is None or not corrected:
            continue
        # Find the original line
        original = next((raw for num, raw, _ in errored_lines if num == ln), "")
        result.append({
            "line_number": ln,
            "original_line": original,
            "corrected_line": corrected,
            "explanation": explanation,
        })

    return result


# ---------------------------------------------------------------------------
# Return code explanation
# ---------------------------------------------------------------------------

_RETURN_EXPLAIN_SYSTEM = """\
You are an ACH payment operations expert. A NACHA return code has been received.
Explain what happened in plain language a bank operations user can act on.
Do NOT invent payment details beyond what is provided.

When vendor payment history is provided, use it to:
- Identify if the routing number or account number looks like a typo compared to prior successful payments.
- Suggest the likely correct value if a near-match is found (e.g. "previous successful payments used routing 021000021 — current routing differs by 1 digit").
- Note recurring patterns if the same vendor has been rejected before.

Respond with a JSON object only — no markdown, no prose.
The object must contain exactly:
{
  "customer_message": "<one sentence a bank can send to the originating company explaining why the payment was returned>",
  "corrective_action": "<one to two sentences describing what the originator should do next, citing specific routing/account correction if history suggests a typo>"
}
"""


def _digits_diff(a: str, b: str) -> int:
    """Count differing characters between two strings of the same length."""
    if len(a) != len(b):
        return max(len(a), len(b))
    return sum(x != y for x, y in zip(a, b))


def _build_vendor_history_context(
    individual_name: str,
    receiving_dfi: str,
    account_masked: str,
) -> str | None:
    """Build a vendor history context string for the LLM prompt.

    Looks up all past payments for the same vendor name, identifies successful
    and failed patterns, and flags routing/account number differences that look
    like typos (differ by 1–2 digits from a previously successful payment).

    Returns None when there is no meaningful history to include.
    """
    try:
        from payment_tracking_agent.ledger import store as _store  # noqa: PLC0415
        from payment_tracking_agent.models.payment import PaymentStatus  # noqa: PLC0415
    except Exception:
        return None

    vendor_name_lower = individual_name.strip().lower()
    all_entries = _store.list_all_entries()
    vendor_entries = [
        e for e in all_entries
        if e.individual_name.strip().lower() == vendor_name_lower
    ]

    if len(vendor_entries) <= 1:
        return None  # only the current payment — no history to compare

    successful_statuses = {
        PaymentStatus.WITH_BENEFICIARY_BANK_PENDING,
        PaymentStatus.WITH_SCHEME_SUBMITTED,
        PaymentStatus.WITH_SCHEME_ACKNOWLEDGED,
    }
    rejected_statuses = {
        PaymentStatus.REJECTED_BY_RETURN_FILE,
        PaymentStatus.REJECTED_BY_SETTLEMENT,
    }

    successful = [e for e in vendor_entries if e.status in successful_statuses]
    rejected   = [e for e in vendor_entries if e.status in rejected_statuses]

    parts: list[str] = []

    # ── Routing number comparison ────────────────────────────────────────
    past_dfis = list({e.receiving_dfi for e in successful if e.receiving_dfi})
    typo_candidates = [
        (dfi, _digits_diff(receiving_dfi, dfi))
        for dfi in past_dfis
        if dfi != receiving_dfi and len(dfi) == len(receiving_dfi)
    ]
    typo_candidates.sort(key=lambda x: x[1])

    if typo_candidates and typo_candidates[0][1] <= 2:
        best_dfi, diff = typo_candidates[0]
        parts.append(
            f"ROUTING MISMATCH — current routing '{receiving_dfi}' differs by {diff} digit(s) "
            f"from '{best_dfi}' used in {len(successful)} prior successful payment(s) to this vendor. "
            "Likely a typo."
        )
    elif any(e.receiving_dfi == receiving_dfi for e in successful):
        parts.append(
            f"This vendor has {len(successful)} prior successful payment(s) to routing '{receiving_dfi}'."
        )
    elif past_dfis:
        parts.append(
            f"Prior successful payments to this vendor used routing(s): {', '.join(past_dfis[:3])}. "
            f"Current payment uses '{receiving_dfi}' — confirm this is correct."
        )

    # ── Account number suffix comparison (masked — last 4 digits only) ──
    past_accounts = list({e.dfi_account_number_masked for e in successful if e.dfi_account_number_masked})
    current_suffix = account_masked[-4:] if len(account_masked) >= 4 else account_masked
    for past_acct in past_accounts:
        past_suffix = past_acct[-4:] if len(past_acct) >= 4 else past_acct
        if past_suffix != current_suffix:
            diff = _digits_diff(current_suffix, past_suffix)
            if diff <= 1:
                parts.append(
                    f"ACCOUNT MISMATCH — current account ending '{current_suffix}' differs by {diff} "
                    f"digit from prior successful account ending '{past_suffix}'. Possible typo."
                )
                break

    # ── Recurring rejection pattern ──────────────────────────────────────
    if rejected:
        past_codes = list({e.return_reason_code for e in rejected if e.return_reason_code})
        if past_codes:
            parts.append(
                f"This vendor has had {len(rejected)} prior rejection(s) with code(s): "
                f"{', '.join(past_codes)}. Recurring issue — verify account details with vendor."
            )

    return "\n".join(parts) if parts else None


def explain_return_code(
    return_code: str,
    return_description: str,
    individual_name: str,
    amount: float,
    receiving_dfi: str = "",
    account_masked: str = "",
) -> dict[str, str]:
    """Call the LLM to explain a NACHA return reason code and suggest a fix.

    When ``receiving_dfi`` and ``account_masked`` are provided, the function
    also fetches vendor payment history from the ledger, runs a fuzzy digit
    comparison against prior successful payments, and passes any typo hints
    to the LLM so it can suggest a specific correction.

    Returns a dict with keys ``customer_message`` and ``corrective_action``.
    Falls back to static text if no LLM key is configured or the call fails.
    """
    fallback = {
        "customer_message": (
            f"Your ACH payment of ${amount:.2f} to {individual_name} was returned "
            f"by the beneficiary bank with reason code {return_code}: {return_description}."
        ),
        "corrective_action": (
            f"Review the return code {return_code} and correct the underlying issue "
            "before resubmitting the payment."
        ),
    }

    _env_anthropic = (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("PTA_ANTHROPIC_API_KEY")
    )
    if not settings.llm_api_key and not settings.anthropic_api_key and not _env_anthropic:
        logger.warning("No LLM key — using static return code explanation for %s.", return_code)
        return fallback

    provider = (settings.llm_provider or "openai").lower()
    model = settings.llm_model
    if provider == "anthropic":
        api_key = settings.anthropic_api_key or settings.llm_api_key or _env_anthropic
    else:
        api_key = settings.llm_api_key or settings.anthropic_api_key or _env_anthropic

    if not api_key:
        return fallback

    # Build vendor history context for typo detection
    vendor_history = ""
    if receiving_dfi or account_masked:
        history_ctx = _build_vendor_history_context(individual_name, receiving_dfi, account_masked)
        if history_ctx:
            vendor_history = f"\n\nVendor payment history analysis:\n{history_ctx}"

    user_message = (
        f"A NACHA ACH payment of ${amount:.2f} to '{individual_name}' was returned.\n"
        f"Return code: {return_code} — {return_description}\n"
        f"Routing used: {receiving_dfi or 'unknown'}\n"
        f"Account (masked): {account_masked or 'unknown'}"
        f"{vendor_history}\n\n"
        "Respond with the JSON object only."
    )

    try:
        raw_text = ""
        if provider == "anthropic":
            from anthropic import Anthropic  # noqa: PLC0415
            client = Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=512,
                system=_RETURN_EXPLAIN_SYSTEM,
                messages=[{"role": "user", "content": user_message}],
            )
            raw_text = response.content[0].text if response.content else ""
        else:
            from openai import OpenAI  # noqa: PLC0415
            client = OpenAI(api_key=api_key, base_url=settings.llm_base_url or None)
            response = client.chat.completions.create(
                model=model,
                max_tokens=512,
                messages=[
                    {"role": "system", "content": _RETURN_EXPLAIN_SYSTEM},
                    {"role": "user", "content": user_message},
                ],
            )
            raw_text = response.choices[0].message.content or ""

        raw_text = _strip_code_fences(raw_text)
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict) and "customer_message" in parsed and "corrective_action" in parsed:
            logger.info("LLM explained return code %s for %s", return_code, individual_name)
            return {
                "customer_message": str(parsed["customer_message"]),
                "corrective_action": str(parsed["corrective_action"]),
            }
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM return code explanation failed: %s", exc, exc_info=True)

    return fallback


# ---------------------------------------------------------------------------
# Pre-submission risk assessment
# ---------------------------------------------------------------------------

_PRE_SUBMISSION_SYSTEM = """\
You are a senior ACH payment risk analyst reviewing payments BEFORE they are
submitted to the ACH scheme. You are given details about a specific payment
and its customer's historical payment signals from the bank's memory.

Your job is to recommend one of three actions:
  PROCEED  — history is clean; submit normally.
  REVIEW   — submit but flag for close monitoring (medium risk signals).
  HOLD     — do NOT submit yet; high risk of rejection or return based on history.

Base your decision on the provided signals. Do NOT invent additional history.
Be specific: cite the signal (e.g. rejection rate, routing mismatch, past R01s)
that drove your recommendation.

Respond with a JSON object only — no markdown, no prose:
{
  "action": "PROCEED" | "REVIEW" | "HOLD",
  "ai_recommendation": "<2–3 sentences: what signal triggered this and what operator should do>"
}
"""


def assess_pre_submission_payment(
    customer_name: str,
    customer_id: str,
    amount: float,
    receiving_dfi: str,
    account_masked: str,
    risk_level: str,
    risk_reason: str,
    historical_total_payments: int,
    historical_rejections: int,
    historical_returns: int,
    rejection_rate_pct: float,
    rejections_last_30d: int,
) -> dict[str, str]:
    """Call the LLM to assess whether a payment should PROCEED, REVIEW, or HOLD.

    Uses the customer's historical risk signals from the in-memory ledger.
    Falls back to a deterministic action when no LLM key is configured.
    """
    # Deterministic fallback based on risk level
    _action_map = {"HIGH": "HOLD", "MEDIUM": "REVIEW", "LOW": "PROCEED"}
    _fallback_action = _action_map.get(risk_level, "PROCEED")
    fallback = {
        "action": _fallback_action,
        "ai_recommendation": (
            f"Deterministic assessment — {risk_level} risk: {risk_reason} "
            "No LLM key configured; using rule-based classification."
        ),
    }

    _env_anthropic = (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("PTA_ANTHROPIC_API_KEY")
    )
    if not settings.llm_api_key and not settings.anthropic_api_key and not _env_anthropic:
        return fallback

    provider = (settings.llm_provider or "openai").lower()
    model = settings.llm_model
    if provider == "anthropic":
        api_key = settings.anthropic_api_key or settings.llm_api_key or _env_anthropic
    else:
        api_key = settings.llm_api_key or settings.anthropic_api_key or _env_anthropic
    if not api_key:
        return fallback

    user_message = (
        f"Payment to assess before scheme submission:\n"
        f"  Vendor/customer : {customer_name} (ID: {customer_id})\n"
        f"  Amount          : ${amount:,.2f}\n"
        f"  Routing         : {receiving_dfi}\n"
        f"  Account (masked): {account_masked}\n\n"
        f"Customer historical signals from bank memory:\n"
        f"  Total past payments    : {historical_total_payments}\n"
        f"  Total rejections       : {historical_rejections}\n"
        f"  Beneficiary-bank returns: {historical_returns}\n"
        f"  Rejection rate         : {rejection_rate_pct:.1f}%\n"
        f"  Rejections last 30 days: {rejections_last_30d}\n"
        f"  Deterministic risk tier: {risk_level} — {risk_reason}\n\n"
        "Recommend PROCEED, REVIEW, or HOLD. Return JSON only."
    )

    try:
        raw_text = ""
        if provider == "anthropic":
            from anthropic import Anthropic  # noqa: PLC0415
            client = Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=300,
                system=_PRE_SUBMISSION_SYSTEM,
                messages=[{"role": "user", "content": user_message}],
            )
            raw_text = response.content[0].text if response.content else ""
        else:
            from openai import OpenAI  # noqa: PLC0415
            client = OpenAI(api_key=api_key, base_url=settings.llm_base_url or None)
            response = client.chat.completions.create(
                model=model,
                max_tokens=300,
                messages=[
                    {"role": "system", "content": _PRE_SUBMISSION_SYSTEM},
                    {"role": "user", "content": user_message},
                ],
            )
            raw_text = response.choices[0].message.content or ""

        raw_text = _strip_code_fences(raw_text)
        parsed = json.loads(raw_text)
        if (
            isinstance(parsed, dict)
            and parsed.get("action") in {"PROCEED", "REVIEW", "HOLD"}
            and "ai_recommendation" in parsed
        ):
            logger.info(
                "Pre-submission assessment: customer=%s action=%s",
                customer_id,
                parsed["action"],
            )
            return {
                "action": str(parsed["action"]),
                "ai_recommendation": str(parsed["ai_recommendation"]),
            }
    except Exception as exc:  # noqa: BLE001
        logger.error("Pre-submission LLM assessment failed: %s", exc, exc_info=True)

    return fallback

