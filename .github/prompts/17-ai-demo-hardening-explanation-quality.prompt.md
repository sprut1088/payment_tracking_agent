# Prompt 17 — AI Demo Hardening and Explanation Quality Presets

Read `.github/copilot-instructions.md` before editing.

Backend, frontend, and documentation only.

## Objective

Harden the Anthropic Claude AI explanation layer so demo output is more consistent, safer, and better aligned with ACH payment operations.

The AI layer is already integrated and working. This prompt should improve explanation quality, not add major new features.

## Current AI Behavior

The app already supports:

- POST `/api/demo-flow/payments/{payment_id}/ai-explanation`
- Anthropic Claude API integration
- `PAYMENT_AGENT_USE_SYSTEM_CERTS=true` for corporate Windows SSL
- AI explanation panel in Live Payment Search detail
- Backend tests that mock Anthropic and do not make network calls
- Guardrails preventing AI from changing payment status/history/evidence
- Sanitization for unsafe `cleared` and unsupported funds-movement wording

## Required Improvements

### 1. Status-Specific Explanation Guidance

Update the AI system/user prompt so Claude gets explicit guidance for each current status.

#### `WITH BENEFICIARY BANK`

Claude should explain:

```text
The CCD file passed bank-side syntax validation.
Settlement summary evidence was received for the batch.
The payment is currently treated as with the beneficiary bank.
Settlement summary is summary-level evidence only.
No payment-level clearing is claimed.
No NACHA return evidence has been matched for this payment.
```

Claude must not say:

```text
cleared
settled at payment level
completed
successfully paid
funds transferred
funds credited
```

#### `REJECTED BY SCHEME`

Claude should explain:

```text
The CCD file passed bank-side syntax validation.
A scheme-reject file matched this payment trace.
The payment was rejected at scheme validation.
The payment should be corrected and resubmitted in a new batch.
```

Claude must not infer root cause beyond the evidence.

Example:
If evidence only says:

```text
Receiving DFI identification failed scheme validation.
```

Claude can say that exact reason, but must not invent:

```text
the routing number is non-existent
the account is closed
the beneficiary bank rejected it
funds were not debited
```

#### `REJECTED BY BENEFICIARY BANK`

Claude should explain:

```text
The CCD file passed bank-side syntax validation.
Settlement summary evidence was received for the batch.
A NACHA return file later matched the original trace number.
The payment is rejected by the beneficiary bank.
The return reason code should drive the next action.
```

Claude must not overwrite or contradict scheme-reject evidence.

### 2. Improve Prompt Quality

Modify the backend AI prompt builder so it provides Claude with a compact, explicit evidence packet:

```text
Current status
Payment identity
Amount
Batch
Trace number
Status history in chronological order
Evidence list in chronological order
Known limitations
Allowed conclusions
Forbidden conclusions
```

The prompt should explicitly say:

```text
Use the current_status as the source of truth.
Do not infer statuses from timestamps.
Do not infer money movement.
Do not infer customer risk history.
Do not infer settlement amount reconciliation.
Do not infer payment-level clearing from settlement summary.
```

### 3. Avoid Overly Precise Timing Claims

Claude should not say things like:

```text
approximately 2 seconds after submission
approximately 41 seconds after submission
```

unless timing is explicitly important.

Add prompt guidance and/or sanitizer protection so the AI avoids demo-distracting timing statements.

Preferred wording:

```text
after CCD upload
later in the flow
after scheme-reject evidence was received
after NACHA return evidence was received
```

### 4. Explanation Quality Presets

Add a small backend concept of explanation presets, without adding major UI complexity.

Support these preset values internally:

```text
operations
customer_safe
executive
```

Default:

```text
operations
```

Behavior:

- `operations`: concise operations explanation with evidence and recommended action.
- `customer_safe`: non-technical customer-facing explanation, no internal jargon unless necessary.
- `executive`: very short summary emphasizing current state, evidence, and next step.

The endpoint may accept an optional request body:

```json
{
  "preset": "operations"
}
```

If no body is provided, preserve current behavior and use `operations`.

Do not break the existing frontend call.

### 5. Frontend UX

In the AI Explanation panel:

- Add a small selector or button group for explanation style:
  - Operations
  - Customer-safe
  - Executive
- Default to Operations.
- The `Generate AI explanation` button should send the selected preset.
- Keep explanations button-triggered only.
- Do not auto-call Claude.
- Do not call Claude in Demo Mode ON.

Add helper text:

```text
Claude explains deterministic ledger evidence. It does not determine payment status.
```

### 6. Output Safety

Keep existing sanitization.

Extend tests so unsafe mocked Claude output is cleaned when it includes:

```text
approximately 2 seconds after submission
approximately 41 seconds after submission
successfully paid
payment completed
funds credited
funds transferred
```

Safe replacements should be evidence-grounded and status-aware.

Do not over-sanitize the required caveat:

```text
Settlement summary is not payment-level clearing evidence.
```

That sentence is allowed.

## Tests

Backend tests must mock Anthropic and must not make real network calls.

Add or update tests proving:

1. Default preset is `operations`.
2. Endpoint accepts `operations`, `customer_safe`, and `executive`.
3. Invalid preset returns a clear 422 or 400-style validation error.
4. Prompt includes status-specific guidance for:
   - `WITH BENEFICIARY BANK`
   - `REJECTED BY SCHEME`
   - `REJECTED BY BENEFICIARY BANK`
5. Prompt tells Claude not to infer money movement.
6. Prompt tells Claude not to infer payment-level clearing from settlement summary.
7. Sanitizer removes or rewrites unsafe timing claims.
8. Sanitizer removes or rewrites unsupported phrases:
   - successfully paid
   - payment completed
   - funds credited
   - funds transferred
9. AI explanation does not mutate payment status/history/evidence.
10. Existing tests still pass.

Frontend build must pass.

## Documentation

Update README Anthropic AI section with a short note:

```text
AI explanation styles
```

Include:

```text
Operations: evidence-based operations explanation and recommended action.
Customer-safe: customer-facing wording without unsupported money-movement claims.
Executive: short status, evidence, and next-step summary.
```

Also restate:

```text
AI explanations are generated on demand only. Claude does not determine payment status.
```

## Do Not Do

Do not change deterministic ledger status logic.
Do not change parser behavior.
Do not change file-driven lifecycle logic.
Do not add database persistence.
Do not add authentication.
Do not add new LLM providers.
Do not auto-call Claude on page load.
Do not expose or log API keys.
Do not disable SSL verification.
Do not remove Demo Mode ON mocked story.
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
- prompt/guardrail improvements
- preset behavior added
- frontend AI style selector behavior
- tests added or updated
- validation result
- confirmation that AI does not mutate ledger status/history/evidence