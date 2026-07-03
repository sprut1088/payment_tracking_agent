# Prompt 09 — Backend CCD Parser and Ledger Foundation

Read `.github/copilot-instructions.md` before editing.

Backend only.

## Objective

Implement the first real file-driven payment ledger foundation.

When the backend scans a CCD file in:

```text
backend/demo-inbox/ccd
```

it should parse ACH CCD entry detail records and create in-memory payment records.

This step only handles CCD parsing and initial ledger creation.

Do not implement settlement parsing.
Do not implement return parsing.
Do not modify frontend source code.

Business Rule

After a CCD file is scanned and bank-side syntax validation passes, parsed payments should move to:

SENT TO SCHEME

Each payment must have evidence explaining:

CCD file uploaded and bank-side syntax validation passed.

If basic syntax validation fails but a payment can still be parsed, classify it as:

WITH BANK

with an evidence explanation.

CCD Parsing Scope

Parse ACH record type 6 entry detail records.

Use fixed-width NACHA positions:

record_type_code              1
transaction_code              2-3
receiving_dfi_identification  4-11
check_digit                   12
dfi_account_number            13-29
amount                        30-39
individual_id_number          40-54
individual_name               55-76
discretionary_data            77-78
addenda_record_indicator      79
trace_number                  80-94

Amounts are in cents.

Mask account numbers in API responses.

Do not store or display full account numbers.

Payment Ledger Model

Add typed backend models for a demo payment ledger.

Each payment should include at minimum:

payment_id
batch_key
source_file
trace_number
transaction_code
receiving_dfi_identification
masked_account_number
amount
individual_id_number
individual_name
current_status
status_history
evidence

Use statuses from .github/copilot-instructions.md:

WITH BANK
SENT TO SCHEME
WITH BENEFICIARY BANK
REJECTED BY SCHEME
REJECTED BY BENEFICIARY BANK
API

Expose a backend endpoint:

GET /api/demo-flow/payments

It should return the current in-memory ledger payments.

Reset should clear the payment ledger.

Existing demo-aflow endpoints must keep working.

Tests

Add backend tests proving:

Seeding/scanning batch_1100.ach creates payment ledger records.
The fixture creates 4 payments if the sample CCD has 4 type 6 records.
Parsed payments have status SENT TO SCHEME.
Parsed payments include trace number, amount, individual name, masked account, and evidence.
GET /api/demo-flow/payments returns the ledger.
Reset clears the ledger.
Existing demo-flow tests still pass.
Do Not Do

Do not implement settlement parser.
Do not implement return parser.
Do not infer clearing.
Do not implement database persistence.
Do not add LLM calls.
Do not modify frontend source code.
Do not add new dependencies.
Do not commit.

Validation

After implementation, these must pass:

python -m pytest
Expected Summary

Summarize:

files changed
parser behavior
ledger model
endpoint added
tests added or updated
validation result