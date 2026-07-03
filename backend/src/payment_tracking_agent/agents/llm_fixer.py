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
    "explanation": "<brief description of what was reconstructed>"
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
    print("LLM fixer called with errored_lines:", errored_lines)
    if not errored_lines:
        return []

    if not settings.llm_api_key and not settings.anthropic_api_key:
        logger.warning("No LLM API key configured — skipping LLM fix suggestions.")
        return []

    provider = (settings.llm_provider or "openai").lower()
    model = settings.llm_model
    max_tok = settings.llm_max_tokens

    # Select the API key for the chosen provider
    print("provider:", provider)
    if provider == "anthropic":
        api_key = settings.anthropic_api_key or settings.llm_api_key
    else:
        api_key = settings.llm_api_key or settings.anthropic_api_key

    if not api_key:
        logger.warning("No API key found for provider '%s' — skipping.", provider)
        return []

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
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
                temperature=0,
                max_tokens=8192,
            )
            print("Anthropic response:", response)
            raw_json = response.content[0].text
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
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            raw_json = response.choices[0].message.content or "{}"
        # Strip markdown code fences — models add them despite being told not to
        raw_json = _strip_code_fences(raw_json)
        print("LLM raw JSON response (stripped):", raw_json[:200])
        payload = json.loads(raw_json)
        # LLM may wrap the array in a key — unwrap if needed
        suggestions: list[dict] = payload if isinstance(payload, list) else next(
            (v for v in payload.values() if isinstance(v, list)), []
        )
    except Exception as exc:
        import traceback
        # Log full stack trace so the root cause is visible in the server console
        logger.error("LLM fix call failed (%s): %s", type(exc).__name__, exc, exc_info=True)
        print("=== LLM ERROR ===")
        print(f"Provider : {provider}")
        print(f"Model    : {model}")
        print(f"Type     : {type(exc).__name__}")
        print(f"Detail   : {exc}")
        traceback.print_exc()

        exc_str = str(exc).lower()
        if "connection" in exc_str or "connect" in exc_str:
            print(
                "HINT: Connection error — check that the host can reach "
                f"{'api.anthropic.com' if provider == 'anthropic' else 'api.openai.com'}. "
                "If behind a corporate proxy, set PTA_LLM_BASE_URL or configure "
                "HTTP_PROXY / HTTPS_PROXY environment variables."
            )
        elif "auth" in exc_str or "401" in exc_str or "403" in exc_str:
            print("HINT: Authentication error — verify your API key is correct and active.")
        elif "rate" in exc_str or "429" in exc_str:
            print("HINT: Rate-limit error — the API key has hit its request quota.")

        print("=================")
        return []

    # Merge back with the original lines so callers always have both sides
    original_map = {ln: raw for ln, raw, _ in errored_lines}
    return [
        {
            "line_number": s.get("line_number"),
            "original_line": original_map.get(s.get("line_number"), ""),
            "corrected_line": s.get("corrected_line", ""),
            "explanation": s.get("explanation", ""),
        }
        for s in suggestions
    ]
