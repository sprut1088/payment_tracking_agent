# Prompt 03 — Update Documentation for SME-Confirmed ACH Flow

Read `.github/copilot-instructions.md` before editing.

Update documentation only. Do not change backend code. Do not change frontend code.

## Objective

Align project documentation with the ACH SME-confirmed payment flow.

The key SME clarification is:

- CCD upload contains individual payment trace numbers.
- If bank-side syntax validation passes, payments move to `SENT TO SCHEME`.
- If bank-side syntax validation fails but traces/customer data can be parsed, payments remain `WITH BANK`.
- If scheme rejects the file or records, payments are `WITH BANK` with status `REJECTED BY SCHEME`.
- FedACH settlement file is summary-level and does not contain individual customer payment details.
- When settlement summary is received, payments in the submitted batch move to `WITH BENEFICIARY BANK`.
- Do not mark individual payments as `CLEARED` from summary-level settlement.
- NACHA return file contains original trace number and rejection reason.
- When return file is matched to original CCD trace number, payment moves to `REJECTED BY BENEFICIARY BANK`.
- AI/LLM explains syntax errors, scheme rejections, return reasons, historical risk, confidence, and recommendations.
- AI memory must store prior successful processing, syntax issues, scheme rejections, return issues, and risk trends.

## Files to Create

Create:

```text
docs/01-business-understanding.md