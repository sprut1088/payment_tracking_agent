# Prompt 11 — Backend NACHA Return Parser and Ledger Updates

Read `.github/copilot-instructions.md` before editing.

Backend only.

## Objective

Update the in-memory payment ledger when NACHA return evidence is detected.

Current behavior:
- `scan-ccd` parses CCD records and creates payments in `SENT TO SCHEME`.
- `check-settlement` applies settlement summary and scheme-reject evidence.
- `check-returns` detects return files, but does not yet update payment ledger statuses.

Required behavior:
- `check-returns` should parse NACHA return evidence.
- Matched returned payments should move to `REJECTED BY BENEFICIARY BANK`.

## Business Rules

Use only these statuses:

- `WITH BANK`
- `SENT TO SCHEME`
- `WITH BENEFICIARY BANK`
- `REJECTED BY SCHEME`
- `REJECTED BY BENEFICIARY BANK`

When a NACHA return file is detected:
- Parse return addenda record type `7` with addenda type `99`.
- Extract return reason code.
- Extract original trace number.
- Match original trace number to ledger payment trace number.
- Move matched non-scheme-rejected payments to `REJECTED BY BENEFICIARY BANK`.
- Append evidence to payment history.

Evidence summary must include:
- return file name
- original trace number
- return reason code
- clear wording that the beneficiary bank returned the payment

Do not overwrite `REJECTED BY SCHEME` with `REJECTED BY BENEFICIARY BANK`.

If a return trace is unmatched:
- Do not create a fake payment.
- Do not modify unrelated payments.
- Optionally record/log unmatched return evidence at batch/file level if existing models support it.

## NACHA Return Parsing Scope

Parse only what is needed for this demo:

Return addenda record type `7`, addenda type `99`.

Use fixed-width positions:
- record_type_code: position 1
- addenda_type_code: positions 2-3
- return_reason_code: positions 4-6
- original_trace_number: positions 7-21
- trace_number: positions 80-94

Only remove line endings before fixed-width slicing.
Do not call strip before slicing.

Do not implement full NACHA return parsing beyond this scope.

## Fixture Alignment

Use the existing return fixture:

demo-data/local-folder-demo/batch_1100/returns/batch_1100_return.ach

Inspect and update it if needed so it contains a valid type `7` addenda type `99` record with original trace number matching a real CCD trace.

Use this returned trace unless there is a strong reason not to:

123456780000002

Do not use the scheme-rejected trace:

123456780000004

Reason:
- 123456780000004 is already used for `REJECTED BY SCHEME`.
- The return demo should show a different payment moving from `WITH BENEFICIARY BANK` to `REJECTED BY BENEFICIARY BANK`.

## Expected Demo Result

After this sequence:

1. clean
2. seed ccd
3. POST /api/demo-flow/reset
4. POST /api/demo-flow/scan-ccd
5. seed settlement
6. POST /api/demo-flow/check-settlement
7. seed returns
8. POST /api/demo-flow/check-returns
9. GET /api/demo-flow/payments

Expected ledger status counts:
- 14 payments = `WITH BENEFICIARY BANK`
- 1 payment = `REJECTED BY SCHEME`
- 1 payment = `REJECTED BY BENEFICIARY BANK`
- 0 payments = `CLEARED`

## API

`GET /api/demo-flow/payments` should show updated return status after:

POST /api/demo-flow/check-returns

Reset should still clear the payment ledger.

Existing demo-flow endpoints must keep working.

## Tests

Add or update backend tests proving:

1. After CCD scan, parsed payments start as `SENT TO SCHEME`.
2. After settlement plus scheme-reject, one payment is `REJECTED BY SCHEME` and the rest are `WITH BENEFICIARY BANK`.
3. After return evidence, the matched return trace moves to `REJECTED BY BENEFICIARY BANK`.
4. The scheme-rejected trace remains `REJECTED BY SCHEME`.
5. Remaining payments stay `WITH BENEFICIARY BANK`.
6. No payment is marked `CLEARED`.
7. Return evidence is appended to payment history.
8. `GET /api/demo-flow/payments` returns the updated return status.
9. Repeat `check-returns` calls are idempotent.

## Do Not Do

Do not implement FedACH settlement parsing.
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

- files changed
- return parser behavior
- return matching behavior
- ledger status updates
- tests added or updated
- validation result