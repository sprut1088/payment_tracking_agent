# Prompt 10 — Backend Settlement and Scheme-Reject Ledger Updates

Read `.github/copilot-instructions.md` before editing.

Backend only.

## Objective

Update the in-memory payment ledger when settlement and scheme-reject evidence is detected.

This step extends the file-driven demo flow after CCD parsing.

Current behavior:
- `scan-ccd` parses CCD records and creates payments in `SENT TO SCHEME`.
- `check-settlement` detects settlement and scheme-reject files, but does not yet update payment statuses.

Required behavior:
- `check-settlement` should update ledger payment statuses using file evidence.

## Business Rules

Use only the SME-confirmed statuses:

- `WITH BANK`
- `SENT TO SCHEME`
- `WITH BENEFICIARY BANK`
- `REJECTED BY SCHEME`
- `REJECTED BY BENEFICIARY BANK`

When settlement summary evidence is found for a batch:
- Move non-rejected payments in that batch from `SENT TO SCHEME` to `WITH BENEFICIARY BANK`.
- Evidence summary must say settlement summary was received.
- Evidence summary must clearly say no payment-level clearing is claimed from summary settlement.

When scheme-reject evidence is found for a batch:
- Match rejected payments by trace number when trace number is present.
- Move matched payments to `REJECTED BY SCHEME`.
- Evidence summary must include the scheme rejection reason if available.
- Do not mark unmatched payments as rejected.

If both settlement and scheme-reject evidence are present:
- Apply scheme rejects to matched payments.
- Move remaining non-rejected payments to `WITH BENEFICIARY BANK`.
- Do not mark any payment as `CLEARED`.

If scheme-reject evidence is present without settlement evidence:
- Move matched payments to `REJECTED BY SCHEME`.
- Leave unmatched payments as `SENT TO SCHEME`.

## Fixture Alignment

The current CCD fixture has 16 type `6` payment records.

Do not force it back to 4 records.

Update the demo scheme-reject fixture if needed so it matches one real CCD trace number.

Use this rejected trace if present in the CCD fixture:

```text
123456780000004
```


## Implementation Guidance

Add a small parser/reader for the scheme-reject JSON fixture.

Expected scheme-reject JSON can include:

batch_id
rejections
payment_trace_number
customer_id
customer_name
amount
reason_code
reason
recommended_action

Do not implement a FedACH settlement parser yet.

For settlement evidence, it is enough in this step to detect that a settlement file exists for the batch and use file presence as summary evidence.

Do not calculate settlement amount.
Do not reconcile settlement totals.
Do not infer clearing.

## API

GET /api/demo-flow/payments should show updated statuses after:

POST /api/demo-flow/check-settlement

Existing demo-flow endpoints must keep working.

Reset should still clear the payment ledger.

## Tests

Add or update backend tests proving:

After CCD scan, all parsed payments start as SENT TO SCHEME.
After settlement-only evidence, payments move to WITH BENEFICIARY BANK.
After scheme-reject-only evidence, matched trace moves to REJECTED BY SCHEME and unmatched payments remain SENT TO SCHEME.
After settlement plus scheme-reject evidence, matched trace moves to REJECTED BY SCHEME and remaining payments move to WITH BENEFICIARY BANK.
No payment is marked CLEARED.
Evidence is appended to payment history when status changes.
GET /api/demo-flow/payments returns updated statuses.
Existing demo-flow tests still pass.

## Do Not Do

Do not implement FedACH settlement parsing.
Do not implement NACHA return parsing.
Do not infer clearing.
Do not implement database persistence.
Do not add LLM calls.
Do not modify frontend source code.
Do not add dependencies.
Do not commit.

## Validation

After implementation, this must pass:

python -m pytest


## Expected Summary

Summarize:

files changed
settlement evidence behavior
scheme-reject matching behavior
ledger status updates
tests added or updated
validation result