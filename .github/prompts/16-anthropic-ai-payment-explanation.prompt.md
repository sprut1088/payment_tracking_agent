# Prompt 16 — Anthropic Claude AI Payment Explanation Layer

Read `.github/copilot-instructions.md` before editing.

Backend and frontend.

## Objective

Integrate a real Anthropic Claude LLM API layer for payment explanations.

The first AI use case is:

```text
Generate an evidence-grounded AI explanation for a selected payment.
```

This should appear in the Live Payment Search detail view in Demo Mode OFF.

Do not use AI to determine payment status.

Payment status must remain deterministic from the existing ledger logic.

## Provider

Use Anthropic Claude through the official Python SDK.

Add the minimal backend dependency if needed:

```text
anthropic
```

Do not hard-code API keys.

Read API configuration from environment variables:

```text
ANTHROPIC_API_KEY
ANTHROPIC_MODEL
```

If `ANTHROPIC_MODEL` is missing, use a safe default constant in code, but make it easy to override with the environment variable.

Never commit secrets.

Never log the API key.

## Required Backend Behavior

Add an AI explanation service that takes one ledger payment and its evidence/history and asks Claude to produce a structured explanation.

Add endpoint:

```text
POST /api/demo-flow/payments/{payment_id}/ai-explanation
```

Reason for POST:

```text
Calling an LLM has cost and latency, so it should not happen automatically through GET page refreshes.
```

The endpoint should:

1. Look up the payment by `payment_id` from the in-memory ledger.
2. If not found, return 404.
3. Build a concise prompt using only the payment ledger data:
   - payment_id
   - batch_key
   - source_file
   - trace_number
   - amount_cents
   - individual_id_number
   - individual_name
   - current_status
   - status_history
   - evidence
4. Call Anthropic Claude.
5. Return a typed response.

## Required Response Shape

Create typed backend response model similar to:

```json
{
  "payment_id": "batch_1100:0002",
  "provider": "anthropic",
  "model": "configured model name",
  "summary": "...",
  "status_explanation": "...",
  "evidence_used": ["...", "..."],
  "limitations": ["..."],
  "recommended_action": "...",
  "customer_safe_message": "...",
  "generated_at": "..."
}
```

## Required AI Guardrails

The system prompt to Claude must include these rules:

```text
You are an ACH payment operations explanation assistant.

You must only explain the deterministic evidence provided.
You must not invent payment status.
You must not invent clearing.
You must not invent return reasons.
You must not invent customer history.
You must not claim a payment is cleared from settlement summary evidence.
Settlement summary is summary-level evidence only.
If current_status is WITH BENEFICIARY BANK, say no return evidence has been matched yet unless evidence says otherwise.
If current_status is REJECTED BY SCHEME, explain that the payment was rejected before beneficiary-bank processing.
If current_status is REJECTED BY BENEFICIARY BANK, explain that a NACHA return matched the original trace.
Use concise, operations-friendly language.
Return valid JSON only.
```

The user prompt should include the actual payment JSON and ask for:

```text
summary
status_explanation
evidence_used
limitations
recommended_action
customer_safe_message
```

## Required Fallback Behavior

If `ANTHROPIC_API_KEY` is not set:

- Do not crash the backend.
- Return a clear 503-style response or typed error saying Anthropic API key is not configured.
- The frontend should show a helpful message:

```text
Claude AI explanation is not configured. Set ANTHROPIC_API_KEY and restart the backend.
```

If the Anthropic call fails:

- Return a clear error.
- Do not change ledger status.
- Do not modify payment evidence.
- Do not retry aggressively.

## Required Frontend Behavior

In Demo Mode OFF Payment Search detail view:

Add a section:

```text
AI Explanation
```

Add button:

```text
Generate AI explanation
```

Behavior:

1. Button calls:

```text
POST /api/demo-flow/payments/{payment_id}/ai-explanation
```

2. Show loading state:

```text
Generating Claude explanation...
```

3. Show returned fields:
   - Summary
   - Status explanation
   - Evidence used
   - Limitations
   - Recommended action
   - Customer-safe message

4. If API key is missing or call fails, show a friendly error.
5. Do not auto-call Claude when opening the detail view.
6. Do not call Claude in Demo Mode ON unless explicitly needed later.
7. Do not replace deterministic evidence/status history.

## Example Explanation Expectations

For `WITH BENEFICIARY BANK`, Claude should say:

```text
Settlement summary evidence was received for the batch, so this payment is currently treated as with the beneficiary bank. The settlement summary is not payment-level clearing evidence, and no return evidence has been matched for this payment.
```

For `REJECTED BY SCHEME`, Claude should say:

```text
The scheme reject evidence matched this payment trace. The payment did not proceed to beneficiary-bank processing and requires correction before resubmission.
```

For `REJECTED BY BENEFICIARY BANK`, Claude should say:

```text
The payment reached beneficiary-bank processing and was later returned through a NACHA return file that matched the original trace number.
```

## Tests

Add backend tests that do not make real Anthropic API calls.

Use a fake/mock AI client.

Tests should prove:

1. Missing payment returns 404.
2. Missing API key returns clear not-configured error.
3. Successful mocked Claude response returns the typed explanation.
4. The service prompt includes settlement-summary caveat.
5. AI explanation does not change payment status.
6. AI explanation does not modify status history or evidence.
7. Existing tests still pass.

Frontend build must pass.

## Documentation

Update README with a short section:

```text
Anthropic Claude AI Explanation Setup
```

Include:

```powershell
$env:ANTHROPIC_API_KEY="your-key-here"
$env:ANTHROPIC_MODEL="your-claude-model-id"
```

Explain:

```text
Set these in the backend terminal before starting uvicorn.
Do not commit API keys.
AI explanations are generated on demand from the Payment Search detail view.
AI does not determine payment status; it explains deterministic evidence.
```

## Do Not Do

Do not use AI to update ledger statuses.
Do not let AI override deterministic evidence.
Do not invent payment history.
Do not implement customer risk history yet.
Do not add database persistence.
Do not add authentication.
Do not call Claude automatically on page load.
Do not commit.

## Validation

After implementation, run:

```powershell
python -m pytest
cd frontend
npm run build
```

## Expected Summary

Summarize:

- files changed
- Anthropic configuration added
- backend AI endpoint added
- frontend AI Explanation panel added
- tests added or updated
- validation result
- confirmation that AI does not update payment status