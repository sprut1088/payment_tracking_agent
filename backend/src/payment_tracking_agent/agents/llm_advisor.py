"""LLM advisor — generates corrective action guidance for rejected ACH payments.

Distinct from ``llm_fixer`` (which fixes file syntax), this agent explains
*why* a payment was rejected and tells operations staff what to do next.

Deduplication strategy
----------------------
Multiple payments rejected for the same reason code will receive the same
suggested action.  The LLM is called once per *unique* reason code, not once
per payment, to minimise latency and API cost.

The function returns a dict mapping ``reason_code → suggested_action``.
If the LLM is not configured, an empty dict is returned and the caller
falls back to the static description from ``models.return_file``.
"""

from __future__ import annotations

import json
import logging

from payment_tracking_agent.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert in ACH payment operations and NACHA rules.
When given a list of ACH rejection reason codes, provide concise, actionable
corrective guidance for operations staff.

For each reason code include:
  1. Likely root cause
  2. Immediate action to take (e.g. contact beneficiary, resubmit, void)
  3. How to prevent recurrence

Keep each suggested_action to 2-4 sentences.

Return a JSON array ONLY — no markdown, no prose.
Each element must have exactly:
  {
    "reason_code": "<string>",
    "suggested_action": "<string>"
  }
"""


def get_corrective_actions(
    unique_rejections: list[tuple[str, str]],
) -> dict[str, str]:
    """Ask the LLM for corrective guidance for each unique rejection reason.

    Args:
        unique_rejections: List of ``(reason_code, reason_text)`` tuples,
                           deduplicated by caller.

    Returns:
        Dict mapping ``reason_code → suggested_action``.
        Returns an empty dict when LLM is unavailable or the call fails.
    """
    if not unique_rejections:
        return {}

    if not settings.llm_api_key:
        logger.warning("PTA_LLM_API_KEY not set — skipping corrective action suggestions.")
        return {}

    try:
        from openai import OpenAI  # noqa: PLC0415
    except ImportError:
        logger.error("openai package not installed.")
        return {}

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url or None,
    )

    reasons_block = "\n".join(
        f"- {code}: {text}" for code, text in unique_rejections
    )
    user_message = (
        "Provide corrective guidance for the following ACH rejection reasons:\n\n"
        + reasons_block
        + "\n\nReturn a JSON array only."
    )

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw_json = response.choices[0].message.content or "{}"
        payload = json.loads(raw_json)
        suggestions: list[dict] = (
            payload
            if isinstance(payload, list)
            else next((v for v in payload.values() if isinstance(v, list)), [])
        )
        return {s["reason_code"]: s["suggested_action"] for s in suggestions if "reason_code" in s}

    except Exception as exc:
        logger.error("LLM corrective action call failed: %s", exc)
        return {}
