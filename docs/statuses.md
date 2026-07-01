# Statuses

## Business statuses

- `WITH BANK`
- `WITH SCHEME`
- `WITH BENEFICIARY BANK`
- `CLEARED`
- `REJECTED`

## Internal sub-statuses (roll up to business statuses)

- `WITH_BANK_NOT_UPLOADED`
- `WITH_BANK_UPLOADED`
- `WITH_BANK_VALIDATING`
- `WITH_BANK_VALIDATION_FAILED`
- `WITH_BANK_READY_FOR_SCHEME`
- `WITH_SCHEME_SUBMITTED`
- `WITH_SCHEME_ACKNOWLEDGED`
- `WITH_BENEFICIARY_BANK_PENDING`
- `CLEARED_BY_SETTLEMENT`
- `REJECTED_BY_RETURN_FILE`
- `RECONCILIATION_EXCEPTION`
- `REVIEW_REQUIRED`

## Truth rules

- Do not mark a payment `CLEARED` without settlement/clearing evidence.
- Do not mark a payment `REJECTED` without NACHA return or explicit rejection
  evidence.
- Submitted-but-unsettled-and-unreturned payments are `WITH BENEFICIARY BANK`,
  never "failed".
- Do not claim real PEP+ behavior without artifact evidence.
- If settlement is summary-level only, do not invent payment-level clearing;
  use an explicit cleared trace list.
- Every status change carries an evidence reference and appears in the
  payment's status timeline.
