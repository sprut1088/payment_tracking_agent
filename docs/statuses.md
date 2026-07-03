# Statuses

This document defines the SME-confirmed payment stage model for the ACH Payment Tracking Agent.

---

## Primary Business Stages

| Stage | Meaning |
|---|---|
| `WITH BANK` | Payment is still with the bank because upload failed, bank-side syntax validation failed, correction is needed, or scheme rejected it. |
| `SENT TO SCHEME` | Payment passed bank-side validation and was sent to the scheme. |
| `WITH BENEFICIARY BANK` | Settlement summary was received and the payment is now considered to be with the beneficiary bank pending any future return. |
| `REJECTED BY BENEFICIARY BANK` | NACHA return file was received and matched to original trace number. |

---

## Secondary Statuses

| Secondary Status | Primary Stage | Meaning |
|---|---|---|
| `SYNTAX_VALIDATION_FAILED` | `WITH BANK` | Bank-side upload syntax validation failed. |
| `READY_FOR_SCHEME` | `WITH BANK` | File is valid and ready to be sent to scheme, but not yet submitted. |
| `SENT_TO_SCHEME` | `SENT TO SCHEME` | Bank-side validation passed and batch was submitted to scheme. |
| `REJECTED_BY_SCHEME` | `WITH BANK` | Scheme rejected the batch or records and returned them for correction. |
| `SETTLEMENT_SUMMARY_RECEIVED` | `WITH BENEFICIARY BANK` | Settlement summary was received, moving submitted payments to beneficiary-bank stage. |
| `AWAITING_RETURN_OR_COMPLETION` | `WITH BENEFICIARY BANK` | Payment is awaiting future beneficiary-bank outcome or operational completion. |
| `RETURNED_R01_INSUFFICIENT_FUNDS` | `REJECTED BY BENEFICIARY BANK` | Return file matched the payment and reason is R01. |
| `RETURNED_OTHER` | `REJECTED BY BENEFICIARY BANK` | Return file matched the payment with another return reason. |

---

## Truth Rules

1. Do not mark individual payments as `CLEARED` from summary-only settlement files.
2. Settlement summary is stage evidence, not item-level clearing evidence.
3. Settlement summary moves submitted payments to `WITH BENEFICIARY BANK`.
4. NACHA return file is item-level rejection evidence.
5. A return file match by original trace number moves the payment to `REJECTED BY BENEFICIARY BANK`.
6. Scheme rejection moves affected payments back to `WITH BANK` with status `REJECTED_BY_SCHEME`.
7. Bank-side syntax rejection keeps extracted payments at `WITH BANK`.
8. AI must not invent payment status.
9. Every status change must have evidence.
10. Every status change must appear in the payment timeline.

---

## Settlement Interpretation

The SME-confirmed FedACH settlement file is summary-level.

It may show:

- settlement date,
- cycle time,
- total count,
- total amount,
- grouping or category,
- net settlement amount.

It does not necessarily show:

- original trace number,
- customer ID,
- customer name,
- beneficiary name,
- individual payment status.

Therefore, individual payment clearing cannot be claimed from this file alone.

---

## Return Interpretation

The NACHA return file contains item-level return details.

The most important matching key is:

`original_trace_number`

When that matches a CCD entry trace number, the payment is rejected by the beneficiary bank.
