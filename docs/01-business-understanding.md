# Business Understanding — ACH Payment Tracking Agent

## 1. Objective

The client wants an end-to-end payment flow tracking system for ACH batch processing.

The system should allow operations users to answer:

> Where is this customer's payment right now?

The system must track individual payments by trace number across batch upload, validation, scheme submission, settlement summary, beneficiary-bank processing, and delayed return files.

---

## 2. Confirmed SME Flow

The ACH SME confirmed the operational flow and expected status tagging.

### Stage 1 — Bank User Uploads CCD Batch File

The bank user uploads a CCD batch file containing individual payment trace numbers.

During upload, the bank performs syntax validation.

Validation examples:

- record length,
- record order,
- file header,
- batch header,
- entry detail records,
- batch control,
- file control,
- total counts,
- debit/credit totals,
- hash totals.

If validation passes, the payments move to:

`SENT TO SCHEME`

If validation fails, but payment traces and customer information can still be extracted, the payments remain:

`WITH BANK`

Example:

If the end-of-file or file control record is missing, but entry records can be parsed, the system should classify extracted payments as `WITH BANK` and explain the file correction needed.

---

### Stage 2 — Scheme Validation

After successful bank-side validation, the payment file is sent to the scheme.

The scheme performs additional validations.

If the scheme rejects the file or records, rejection evidence comes back to the initiator bank.

The payment stage should be:

`WITH BANK`

The secondary status should be:

`REJECTED BY SCHEME`

The AI model should explain:

- what was rejected,
- why it was rejected,
- what correction is needed,
- whether the issue is syntax, formatting, missing data, or scheme-level validation.

---

### Stage 3 — Settlement Summary Received

If scheme validation passes, the scheme forwards the payment file to the beneficiary bank.

The scheme sends a FedACH settlement file or settlement summary to the initiator bank.

The SME confirmed that this settlement file is a summary file. It may contain total transactions settled across a sort code, settlement category, settlement window, or another standard grouping.

It does not provide customer-level or payment-level clearing details.

Therefore, when the settlement summary is received, all payments sent in the batch should move to:

`WITH BENEFICIARY BANK`

The system should not mark individual payments as `CLEARED` based only on this summary.

---

### Stage 4 — Beneficiary Bank Return

The beneficiary bank can return a payment later.

The return may come:

- later in the day,
- in the next run,
- next day,
- next week,
- or at another future point.

The NACHA return file contains item-level return information.

The return file includes original payment trace number and rejection reason.

The system should match:

`return.original_trace_number`

to:

`ccd.entry.trace_number`

When a match is found, the payment should be marked:

`REJECTED BY BENEFICIARY BANK`

---

## 3. Business Status Model

### Primary Stage

| Primary Stage | Meaning |
|---|---|
| `WITH BANK` | Payment is still with the bank because upload failed, syntax validation failed, correction is needed, or scheme rejected it. |
| `SENT TO SCHEME` | Payment passed bank-side validation and was sent to scheme. |
| `WITH BENEFICIARY BANK` | Settlement summary was received, meaning the payment has moved beyond scheme and is awaiting beneficiary-bank outcome. |
| `REJECTED BY BENEFICIARY BANK` | NACHA return file was received and matched to original trace number. |

### Secondary Status

| Secondary Status | Parent Stage |
|---|---|
| `SYNTAX_VALIDATION_FAILED` | `WITH BANK` |
| `READY_FOR_SCHEME` | `WITH BANK` |
| `SENT_TO_SCHEME` | `SENT TO SCHEME` |
| `REJECTED_BY_SCHEME` | `WITH BANK` |
| `SETTLEMENT_SUMMARY_RECEIVED` | `WITH BENEFICIARY BANK` |
| `AWAITING_RETURN_OR_COMPLETION` | `WITH BENEFICIARY BANK` |
| `RETURNED_R01_INSUFFICIENT_FUNDS` | `REJECTED BY BENEFICIARY BANK` |
| `RETURNED_OTHER` | `REJECTED BY BENEFICIARY BANK` |

---

## 4. Important Settlement Interpretation

A key SME clarification is that the settlement file is summary-level.

This means it may show:

- total transactions,
- total amount,
- settlement category,
- sort-code grouping,
- settlement window,
- net settlement amount.

It does not necessarily show:

- customer ID,
- customer name,
- original trace number,
- individual payment amount by customer,
- exact list of cleared payments.

Therefore:

> Settlement summary is stage evidence, not individual clearing evidence.

Receipt of settlement summary should move payments to:

`WITH BENEFICIARY BANK`

It should not move payments to:

`CLEARED`

unless explicit item-level clearing evidence is provided in a future artifact.

---

## 5. Return File Interpretation

The NACHA return file is item-level evidence.

It contains:

- returned entry detail,
- return addenda,
- original trace number,
- return reason code,
- return trace number,
- return amount,
- returning bank information.

This allows deterministic matching to the original CCD payment.

Primary match key:

`original_trace_number`

Secondary match keys:

- amount,
- receiving DFI,
- account number,
- receiving company name,
- company ID,
- batch number,
- effective date.

When a return file record matches a payment trace, that payment should move to:

`REJECTED BY BENEFICIARY BANK`

---

## 6. AI and Agentic Role

The AI model should not invent payment status.

The AI should explain and reason over deterministic evidence.

### AI Use Cases

1. CCD upload analysis
   - read CCD file,
   - identify syntax problems,
   - explain file errors,
   - recommend correction,
   - estimate confidence of successful processing.

2. Historical risk analysis
   - remember prior successful payments,
   - remember scheme rejections,
   - remember beneficiary-bank returns,
   - identify customer or beneficiary rejection trends,
   - flag risky payments upfront.

3. Scheme rejection explanation
   - understand scheme rejection reason,
   - classify rejection,
   - recommend correction.

4. Beneficiary return explanation
   - read NACHA return reason,
   - explain business meaning,
   - suggest next action.

5. Batch confidence scoring
   - assess whether the batch is likely to process successfully,
   - call out high-risk records,
   - explain evidence limitations.

---

## 7. AI Memory Requirement

The system should maintain operational memory.

Memory should include:

- payment trace history,
- customer payment history,
- beneficiary payment history,
- prior syntax failures,
- scheme rejection history,
- beneficiary-bank return history,
- return reason trends,
- successful processing history,
- previous recommendations,
- risk scores,
- confidence scores.

This memory should allow the system to say:

> This customer or beneficiary has recent returns for insufficient funds. Review before submission.

The memory must be evidence-based and auditable.

---

## 8. Dashboard Requirements

### Batch Dashboard

The batch dashboard should show all payments within a batch.

Fields:

- batch ID,
- file name,
- upload time,
- trace number,
- customer ID,
- customer name,
- beneficiary name,
- amount,
- current stage,
- secondary status,
- risk level,
- return reason,
- last event,
- recommended action.

### Customer Dashboard

The customer dashboard should show all payments for a customer across batches.

Fields:

- customer ID,
- customer name,
- batch ID,
- trace number,
- amount,
- stage,
- return history,
- rejection trend,
- confidence,
- recommendation.

### Payment Detail View

The payment detail view should show:

- current stage,
- timeline,
- CCD evidence,
- syntax validation evidence,
- scheme evidence,
- settlement summary evidence,
- return evidence,
- AI explanation,
- recommended action.

---

## 9. Example Flow

Assume a CCD file contains four payments:

| Trace | Customer | Amount |
|---|---|---:|
| T001 | Customer A | 100 |
| T002 | Customer B | 100 |
| T003 | Customer C | 100 |
| T004 | Customer D | 100 |

Total batch amount:

`400`

### Upload Passed

All payments move to:

`SENT TO SCHEME`

### Settlement Summary Received

Settlement summary confirms batch-level settlement activity.

All four payments move to:

`WITH BENEFICIARY BANK`

The system does not mark any individual payment as cleared because settlement is summary-level.

### Later Return File Received

Return file contains:

| Original Trace | Reason |
|---|---|
| T004 | R01 - Insufficient Funds |

The system matches T004 to the original CCD entry.

Final statuses:

| Trace | Status |
|---|---|
| T001 | WITH BENEFICIARY BANK |
| T002 | WITH BENEFICIARY BANK |
| T003 | WITH BENEFICIARY BANK |
| T004 | REJECTED BY BENEFICIARY BANK |

If the business later provides explicit completion or item-level clearing evidence, then T001/T002/T003 can be moved to a final cleared/completed status. Until then, their confirmed stage remains `WITH BENEFICIARY BANK`.

---

## 10. Design Principle

Every payment status must be evidence-backed.

The system should always be able to answer:

- What is the current stage?
- What event caused the stage?
- What file or artifact supports it?
- Which agent applied the update?
- What confidence level is assigned?
- What is the recommended next action?
