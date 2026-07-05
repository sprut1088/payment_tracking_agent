# Prompt 18 — AI Payment Risk Classification

Read `.github/copilot-instructions.md` before editing.

Backend, frontend, and documentation.

## Objective

Add an on-demand AI payment risk classification layer using Anthropic Claude.

This prompt adds payment-level operational risk assessment only.

Do not implement batch-level or customer-level risk yet.

Do not change deterministic payment status logic.

## Current State

The application already supports:

- File-driven ACH payment ledger
- CCD parsing
- settlement summary evidence
- scheme-reject evidence
- NACHA return evidence
- live Payment Search detail view
- Anthropic Claude AI explanations
- AI explanation presets
- `PAYMENT_AGENT_USE_SYSTEM_CERTS=true`
- AI guardrails and sanitization
- tests that mock Anthropic and do not make real network calls

## New AI Use Case

For a selected payment, generate an AI operational risk assessment based only on deterministic ledger evidence.

Add endpoint:

```text
POST /api/demo-flow/payments/{payment_id}/ai-risk
```

The risk assessment must be generated on demand only.

Do not call Claude automatically on page load.

## Risk Scope

This is operational payment-follow-up risk, not credit risk and not fraud risk.

Use these risk levels:

LOW
MEDIUM
HIGH

Use a confidence field:

LOW
MEDIUM
HIGH

Risk classification should consider:

current_status
status_history
evidence
scheme reject evidence
NACHA return evidence
missing evidence
whether the payment is still awaiting possible returns
whether correction/resubmission is needed

## Status-Specific Risk Guidance
SENT TO SCHEME

Likely risk:

MEDIUM

Reasoning:

Payment has passed bank-side syntax validation and was sent to scheme.
Scheme/settlement/return evidence may not be available yet.
The risk is uncertainty due to pending downstream evidence.

## WITH BENEFICIARY BANK

Likely risk:

MEDIUM

Reasoning:

Settlement summary evidence was received for the batch.
Settlement summary is not payment-level clearing evidence.
No NACHA return evidence has been matched yet.
Returns may still arrive later.

## REJECTED BY SCHEME

Likely risk:

HIGH

Reasoning:

Scheme reject evidence matched the payment trace.
Payment did not proceed to beneficiary-bank processing.
Correction is required before resubmission.

## REJECTED BY BENEFICIARY BANK

Likely risk:

HIGH

Reasoning:

NACHA return evidence matched the original trace number.
Payment requires follow-up before resubmission.
Return reason code should drive the next action.
WITH BANK

Likely risk:

MEDIUM or HIGH

Reasoning:

Payment is still with bank due to validation or correction state.
Severity depends on evidence.
Required Backend Response Model

Create a typed response similar to:

{
  "payment_id": "batch_1100:0002",
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514",
  "risk_level": "HIGH",
  "confidence": "HIGH",
  "summary": "...",
  "risk_drivers": ["...", "..."],
  "evidence_used": ["...", "..."],
  "limitations": ["...", "..."],
  "recommended_action": "...",
  "generated_at": "..."
}
##  Required AI Guardrails

The Claude system prompt must include:

You are an ACH payment operations risk assistant.

You classify operational payment-follow-up risk only.
You do not classify credit risk.
You do not classify fraud risk.
You do not infer customer financial health.
You do not infer customer history unless provided in evidence.
You do not determine payment status.
Use current_status as the source of truth.
Use only the deterministic ledger evidence provided.
Do not invent settlement, clearing, return, or reject evidence.
Do not infer money movement.
Do not claim funds were debited, credited, transferred, or not transferred unless explicit evidence says so.
Do not claim payment-level clearing from settlement summary.
Settlement summary is summary-level evidence only.
Return valid JSON only.

## Required Sanitization

Reuse or extend existing AI output sanitization.

Ensure returned risk text does not contain unsafe unsupported wording such as:

payment cleared
successfully paid
payment completed
funds credited
funds transferred
funds debited
fraud risk
credit risk
customer is risky
customer lacks funds

Allowed wording:

operational risk
payment follow-up risk
resubmission risk
evidence confidence
return evidence
scheme-reject evidence

## Missing API Key Behavior

If ANTHROPIC_API_KEY is missing:

Return the same style of clear not-configured error used by AI explanation.
Do not crash backend.
Do not change ledger state.

## Frontend Behavior

In Demo Mode OFF Payment Search detail view:

Add a new section:

AI Risk Assessment

Add button:

Generate risk assessment

Behavior:

Button calls:
POST /api/demo-flow/payments/{payment_id}/ai-risk
Show loading state:
Generating Claude risk assessment...
Show returned fields:
Risk level
Confidence
Summary
Risk drivers
Evidence used
Limitations
Recommended action
Show helper text:
Claude classifies operational payment-follow-up risk from deterministic ledger evidence. It does not determine payment status, credit risk, or fraud risk.
If API key is missing or call fails, show a friendly error.
Do not auto-call Claude when opening detail.
Do not call Claude in Demo Mode ON.
Do not replace deterministic status history or evidence.

## Tests

Backend tests must mock Anthropic and must not make real network calls.

Add tests proving:

Missing payment returns 404.
Missing API key returns clear not-configured error.
Successful mocked Claude response returns typed risk assessment.
Prompt includes operational-risk-only guardrails.
Prompt says not credit risk and not fraud risk.
Prompt says current_status is source of truth.
Prompt says not to infer money movement.
Prompt says not to claim payment-level clearing from settlement summary.
Sanitizer removes unsafe unsupported wording.
AI risk assessment does not mutate payment current_status.
AI risk assessment does not mutate status_history.
AI risk assessment does not mutate evidence.
Existing tests still pass.

Frontend build must pass.

## Documentation

Update README with a short section:

## AI Payment Risk Assessment

Explain:

Risk assessment is generated on demand from Payment Search detail.
Risk means operational payment-follow-up risk.
It is not credit risk or fraud risk.
Claude does not determine payment status.
Claude uses deterministic ledger evidence only.


## Do Not Do

Do not implement batch-level risk yet.
Do not implement customer-level risk yet.
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

python -m pytest
cd frontend
npm run build


## Expected Summary

Summarize:

files changed
backend AI risk endpoint added
risk model/guardrails added
frontend AI Risk Assessment panel added
tests added or updated
validation result
confirmation that AI risk does not mutate ledger status/history/evidence