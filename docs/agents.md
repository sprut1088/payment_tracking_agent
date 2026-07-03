# Agents

This document defines the ACH Payment Tracking Agent responsibilities based on the SME-confirmed payment flow.

The agents must use deterministic evidence to update the payment status ledger. AI may explain, summarize, and recommend, but AI must not invent status.

---

## BeforePaymentSubmissionAgent

### Purpose

Analyze the CCD upload before or during bank-side submission.

### Responsibilities

- Parse CCD upload file.
- Extract individual payment trace numbers where possible.
- Extract customer and beneficiary details where possible.
- Run syntax validation.
- Create payment ledger records for parsed payment entries.
- If validation fails, keep extracted payments at `WITH BANK`.
- If validation passes, move payments to `SENT TO SCHEME`.
- Run historical risk analysis using AI memory.
- Flag customers or beneficiaries with recent returns or rejections.
- Produce correction guidance for syntax issues.

### Outputs

- parsed payment entries,
- validation status,
- syntax findings,
- payment ledger records created,
- historical risk findings,
- confidence score,
- recommended action.

---

## SchemeValidationAgent

### Purpose

Process scheme-level acceptance or rejection evidence.

### Responsibilities

- Read scheme rejection artifacts when available.
- Classify rejection reason.
- Match scheme rejection to batch or records.
- Move affected payments to primary stage `WITH BANK`.
- Apply secondary status `REJECTED_BY_SCHEME`.
- Ask AI explanation layer to produce correction guidance.

### Outputs

- rejected batch or records,
- rejection reason,
- affected payment traces if available,
- correction recommendation,
- ledger status updates.

---

## AfterSettlementAgent

### Purpose

Process FedACH settlement summary evidence.

### Responsibilities

- Read FedACH settlement summary or settlement report.
- Extract settlement date, cycle, count, amount, grouping, and direction where available.
- Treat settlement summary as evidence that the batch progressed to beneficiary-bank stage.
- Move submitted payments in the batch to `WITH BENEFICIARY BANK`.
- Do not mark individual payments as `CLEARED` from summary-only settlement.
- Record settlement summary as batch-level evidence.

### Outputs

- settlement summary parsed,
- affected batch IDs,
- payments moved to `WITH BENEFICIARY BANK`,
- evidence limitations,
- confidence score.

### Important Rule

This agent must not claim individual payments are cleared unless future item-level clearing evidence explicitly identifies trace numbers.

---

## ReturnFileAgent

### Purpose

Process NACHA return files from beneficiary banks.

### Responsibilities

- Parse NACHA return file.
- Extract original trace number.
- Extract return reason code.
- Extract return trace number and return amount.
- Match original trace number back to CCD payment record.
- Move matched payment to `REJECTED BY BENEFICIARY BANK`.
- Store return reason and file evidence in the ledger.
- Update AI memory for future risk scoring.
- Generate customer-safe return explanation.

### Outputs

- return records parsed,
- matched payments,
- unmatched returns,
- return reason interpretation,
- ledger status updates,
- customer-friendly message,
- recommended action.

---

## AIExplanationAgent

### Purpose

Explain deterministic ACH evidence and recommend next action.

### Responsibilities

- Explain CCD syntax errors.
- Explain scheme rejection reasons.
- Explain NACHA return reason codes.
- Summarize historical rejection patterns.
- Produce risk and confidence narratives.
- Generate customer-safe wording.
- Provide next-best-action recommendation.
- State evidence limitations clearly.

### Rules

- Do not invent payment status.
- Do not infer individual clearing from settlement summary.
- Do not claim real PEP+ behavior without input evidence.
- Keep customer messages non-technical and bank-approved where possible.

---

## PaymentLifecycleOrchestrator

### Purpose

Coordinate the end-to-end payment lifecycle across configurable batch cycles.

### Responsibilities

- Load demo scenario configuration.
- Run cycles such as 10:00, 10:02, 10:04, 10:06.
- Invoke agents in the correct order.
- Maintain payment status ledger.
- Emit event log.
- Emit agent trace.
- Support batch, customer, date, and payment detail views.

### Outputs

- simulation state,
- payment ledger state,
- batch dashboard view,
- customer dashboard view,
- payment detail view,
- agent trace,
- evidence packet.
