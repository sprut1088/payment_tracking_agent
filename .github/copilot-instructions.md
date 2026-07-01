# GitHub Copilot Instructions — ACH Payment Tracking Agent

## Project Mission

This project builds an end-to-end ACH payment flow tracking and intelligence platform.

The goal is to help bank operations users answer:

> Where is this customer's ACH payment right now?

The system tracks payment status across the full ACH lifecycle:

1. CCD file preparation and upload
2. Bank-side syntax validation
3. PEP+ / ACH processing-engine validation
4. Submission to scheme
5. Movement to beneficiary bank
6. FedACH settlement confirmation
7. Delayed NACHA return-file processing
8. Historical rejection / risk analysis
9. Customer-friendly explanation and corrective action

The project must be demoable through a frontend UI, not only backend APIs or CLI commands.

---

## Business Context

ACH payments are processed in batches.

A CCD upload file may contain many payment records. The bank user uploads the CCD file into the bank system and submits it for clearing. The file is then picked up by Fiserv PEP+ or another ACH processing engine for validation and onward submission.

After validation, valid payment entries are sent to the scheme. The scheme sends those payments to beneficiary banks. Beneficiary banks may clear some payments quickly and may hold or reject other payments. Settlement evidence may come back within minutes, but returns may arrive later in N+1, N+2, N+3, or N+n batch cycles.

This creates a visibility gap.

For example:

- A 10:00 GMT batch contains 20 payments.
- 18 payments are cleared and appear in settlement evidence.
- 2 payments are not in settlement and not yet in a return file.
- Those 2 payments should be marked as `WITH BENEFICIARY BANK`, not failed.
- A later 14:00 GMT batch may include a NACHA return file for the 2 records from the 10:00 GMT batch.
- At that point, those payments should move from `WITH BENEFICIARY BANK` to `REJECTED`.

The client needs payment-level tracking, not just file-level or batch-level tracking.

---

## Core Business Question

The platform must help users answer:

- Where is this payment right now?
- Which batch did it belong to?
- Has the payment been uploaded?
- Has it passed bank-side validation?
- Has it been sent to scheme?
- Has it reached beneficiary bank?
- Has it cleared?
- Has it been rejected?
- If not cleared or rejected, where is it currently?
- What evidence supports the status?
- Has this customer or beneficiary recently had similar rejections?
- What corrective action should be taken?

---

## Core Business Statuses

Use these business-facing statuses:

- `WITH BANK`
- `WITH SCHEME`
- `WITH BENEFICIARY BANK`
- `CLEARED`
- `REJECTED`

Internal sub-statuses are allowed, but they must roll up to the above business statuses.

Recommended internal sub-statuses:

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

---

## Status Truth Rules

These rules are mandatory.

Do not claim a payment is `CLEARED` unless settlement, clearing, or equivalent evidence supports it.

Do not claim a payment is `REJECTED` unless NACHA return evidence or explicit rejection evidence supports it.

Do not claim real PEP+ behavior unless an input artifact provides that evidence.

If a payment was submitted to the scheme but is not present in settlement evidence and is not present in return evidence, mark it as:

`WITH BENEFICIARY BANK`

Do not mark it as failed.

If settlement evidence is summary-level only, do not invent transaction-level clearing. Clearly state the limitation and use a PoC-specific synthetic detail file or explicit cleared trace list if payment-level clearing must be demonstrated.

All status changes must include evidence.

Every payment must have a status timeline.

---

## Key Artifacts

The system works with these input artifacts.

### 1. CCD Customer Upload File

The CCD file is a fixed-width ACH file.

Relevant record types:

- `1` = File Header
- `5` = Batch Header
- `6` = Entry Detail
- `8` = Batch Control
- `9` = File Control

Each type `6` entry detail record becomes one tracked payment.

The parser must extract at minimum:

- file name
- file creation date
- file creation time
- company ID
- company name
- batch number
- effective entry date
- SEC code
- trace number
- transaction code
- receiving DFI identification
- check digit
- receiving account number, masked
- amount
- receiving company ID number
- receiving company name

### 2. FedACH Settlement Report

The FedACH settlement report may contain:

- `10` = Header segment
- `20` = Summary data segment
- `30` = Grand trailer / net adjustment segment

It is used to determine:

- settlement date
- settlement cycle time
- item count
- settlement category
- gross amount
- net settlement amount

Important limitation:

If the settlement file only contains summary-level counts and totals, do not assume which exact trace numbers cleared. For payment-level demo, use a synthetic settlement detail artifact or explicit cleared payment list.

### 3. NACHA Return File

The NACHA return file may contain:

- `1` = File Header
- `5` = Batch Header
- `6` = Returned Entry Detail
- `7` = Return Addenda
- `8` = Batch Control
- `9` = File Control

Return addenda record type `7` with addenda type `99` contains:

- return reason code
- original trace number
- date of ODFI return
- original receiving DFI
- return trace number

Return files may arrive in later cycles and must be correlated back to prior payments using original trace number.

### 4. Historical Payment Records

Historical payment records are used for early failure identification.

The system should identify:

- similar prior payments
- recent returns
- recurring R01 insufficient-funds patterns
- customer-level rejection trends
- beneficiary-level rejection trends
- prior successful payments

Historical analysis must be evidence-based. The LLM may summarize the trend but must not invent history.

### 5. PEP+ / Processing-Engine Status Evidence

For this PoC, PEP+ or processing-engine evidence may be represented as mock JSON.

Do not assume real PEP+ file formats.

Use generic naming such as “ACH processing engine” where appropriate, but allow the demo to label it as PEP+ if required.

---

## Batch Cycle Requirements

The real-world batch cycles are:

- 10:00 GMT
- 14:00 GMT
- 18:00 GMT

The demo must also support accelerated configurable cycles, such as:

- 10:00
- 10:02
- 10:04
- 10:06

The demo cycle schedule must be configurable.

Do not hard-code the system to only 10:00, 14:00, and 18:00.

The simulator should support:

- realistic day schedule
- accelerated 2-minute demo schedule
- accelerated 4-minute demo schedule
- manually configured cycle times
- run-next-cycle mode without waiting for real time

---

## Demo Scenario Behavior

The demo must be able to show this story:

### 10:00 Demo Cycle

- CCD file uploaded with 20 payment records.
- File passes basic syntax validation.
- Historical analysis flags risky payments.
- File is sent to scheme after processing-engine validation.
- Settlement evidence confirms 18 payments cleared.
- 2 payments are not cleared and not returned.
- Those 2 payments are marked `WITH BENEFICIARY BANK`.

### 10:02 Demo Cycle

- New CCD file uploaded with 15 payment records.
- Settlement evidence confirms 12 payments cleared.
- NACHA return file arrives for the 2 pending payments from the 10:00 cycle.
- The 2 previous payments move from `WITH BENEFICIARY BANK` to `REJECTED`.

### Later Demo Cycles

- Additional batches can be processed.
- Returns can continue to arrive for earlier batches.
- Dashboard should show status across batches and customers.

---

## Agent Architecture

Build the solution as a multi-agent workflow.

### 1. BeforePaymentSubmissionAgent

Responsibilities:

- Parse CCD file.
- Run syntax validation.
- Create payment records.
- Stamp initial status as `WITH BANK`.
- Run historical similarity analysis.
- Flag recent or recurring rejection risk.
- Identify syntax errors.
- Provide user correction guidance before submission.

Output should include:

- validation status
- syntax findings
- historical-risk findings
- payment records created
- recommended user action

### 2. AfterPaymentSubmissionAgent

Responsibilities:

- Consume processing-engine / PEP+ status evidence.
- Update submitted payments to `WITH SCHEME`.
- Read settlement evidence.
- Determine cleared versus pending payment status.
- Mark cleared payments as `CLEARED`.
- Mark submitted but uncleared and unreturned payments as `WITH BENEFICIARY BANK`.
- Identify reconciliation exceptions.

Output should include:

- scheme submission status
- settlement summary
- cleared count
- pending count
- reconciliation findings
- status updates applied

### 3. ReturnFileAgent

Responsibilities:

- Parse NACHA return file.
- Extract return reason code.
- Extract original trace number.
- Link return back to original payment.
- Mark payment as `REJECTED`.
- Produce root cause and customer-safe corrective guidance.
- Identify whether this is part of a recurring rejection trend.

Output should include:

- return records parsed
- original payments matched
- unmatched returns
- rejection status updates
- customer-friendly message
- recommended action

### 4. PaymentLifecycleOrchestrator

Responsibilities:

- Run the lifecycle across configured demo cycles.
- Maintain the payment status ledger.
- Coordinate before-submission, after-submission, and return-file agents.
- Produce batch, customer, date, and payment-detail views.
- Maintain an event log and agent trace.

### 5. AIExplanationAgent

Responsibilities:

- Explain deterministic evidence.
- Generate customer-safe messages.
- Summarize trends.
- Suggest next-best action.
- Never invent payment status.
- Always include source limitations where evidence is missing.

---

## Payment Status Ledger

The status ledger is central to the system.

Every CCD type `6` entry must become a payment tracking record.

Each payment record should include:

- payment tracking ID
- trace number
- batch ID
- batch cycle
- source file name
- company ID
- customer ID if available
- customer name if available
- beneficiary name
- receiving DFI
- masked account
- amount
- current status
- status since
- status history
- return reason code
- risk level
- risk reason
- evidence references

Every status history event should include:

- timestamp
- status
- source artifact
- source agent
- evidence summary
- reason

---

## Dashboard Requirements

The system must include a frontend demo UI.

The UI should support these views.

### 1. Demo Simulator View

Purpose:

Run and visualize configurable ACH batch cycles.

Must include:

- scenario selector
- cycle schedule configuration
- current simulated time
- current active cycle
- start simulation
- run next cycle
- pause
- reset
- event log
- status summary cards
- agent trace panel

### 2. Batch Dashboard

Purpose:

Show payments by batch.

Filters:

- batch ID
- cycle time
- file name
- date
- status
- return code

Columns:

- batch ID
- cycle time
- payment ID / trace number
- customer ID
- customer name
- beneficiary name
- amount
- current status
- risk flag
- return code
- last event
- recommended action

### 3. Customer Dashboard

Purpose:

Show all payments for a customer across batches and dates.

Filters:

- customer ID
- customer name
- beneficiary name
- date range
- status
- return code

Columns:

- customer ID
- customer name
- payment ID
- trace number
- batch ID
- batch time
- amount
- current status
- status timeline
- return code
- historical rejection count
- last rejection date
- recommended action

### 4. Payment Search / Detail View

Purpose:

Find one payment and explain its status.

Must show:

- current status
- status timeline
- CCD evidence
- settlement evidence
- return evidence
- historical-risk evidence
- agent trace
- customer-friendly explanation
- next-best action

---

## Frontend Technical Requirements

Use:

- React
- TypeScript
- Vite
- plain CSS, CSS modules, or lightweight styling

Frontend location:

```text
frontend/
