# GitHub Copilot Instructions — ACH Payment Tracking Agent

## Project Mission

This project builds an end-to-end ACH payment flow tracking and intelligence platform.

The goal is to help bank operations users answer:

> Where is this customer's ACH payment right now?

The system tracks ACH payment status across batch upload, bank validation, scheme submission, settlement-summary evidence, beneficiary-bank returns, and AI-assisted explanation.

The project must be demoable through a frontend UI, not only backend APIs or CLI commands.

---

## Current Repository Context

Repository name:

```text
payment_tracking_agent
```

Backend Python package import path:

```text
payment_tracking_agent
```

Correct backend server command:

```powershell
cd backend
python -m uvicorn payment_tracking_agent.main:app --reload --port 8000
```

Frontend command:

```powershell
cd frontend
npm run dev
```

Frontend build command:

```powershell
cd frontend
npm run build
```

Backend test command:

```powershell
cd backend
python -m pytest
```

Do not use the old package name `ach_tracking`.

---

## Business Context

ACH payments are processed in batches.

A CCD upload file may contain many payment records. A bank user uploads the CCD file into the bank system. The bank validates the file syntax. If validation passes, the payments are submitted to the ACH scheme.

The ACH scheme performs its own validations. Some records or batches may be rejected by the scheme and returned to the bank for correction.

If the scheme accepts the file and sends payments onward, the scheme provides settlement evidence to the initiator bank. In this PoC, the FedACH settlement report is summary-level evidence. It contains totals and counts, not customer-level or payment-level clearing confirmation.

Beneficiary banks may later return payments using NACHA return files. Return files can arrive later the same day, in later batch cycles, next day, or N+n days later. Return files contain original trace information that must be matched back to the original payment.

This creates the central visibility gap:

> The bank needs to know where each customer's ACH payment is right now, even when the available evidence is batch-level, summary-level, delayed, or incomplete.

---

## SME-Confirmed Lifecycle

The SME-confirmed ACH tracking flow for this PoC is:

1. Bank user uploads CCD batch file.
2. Bank-side syntax validation happens at upload.
3. If syntax validation passes, parsed payments move to `SENT TO SCHEME`.
4. If bank-side validation fails but payment/customer details can be parsed, classify the affected payment or batch as `WITH BANK`.
5. The scheme performs validation.
6. If the scheme rejects a batch or record, the reject file comes back to the bank. Matched payments become `REJECTED BY SCHEME`.
7. If scheme validation passes and the file is sent onward, the scheme sends a summary settlement file to the initiator bank.
8. The FedACH settlement file is summary-level evidence only.
9. On settlement-summary receipt, submitted payments in the batch move to `WITH BENEFICIARY BANK`.
10. Do not mark individual payments as cleared from summary settlement.
11. A beneficiary bank may later return a payment through a NACHA return file.
12. A NACHA return file contains the original payment trace number and return reason.
13. Matched returned payments become `REJECTED BY BENEFICIARY BANK`.
14. Payments not returned remain `WITH BENEFICIARY BANK` unless stronger evidence later changes their status.

---

## Core Business Question

The platform must help users answer:

- Where is this payment right now?
- Which CCD batch did it belong to?
- Did the CCD upload pass bank-side validation?
- Was the payment sent to scheme?
- Did the scheme reject it?
- Has settlement-summary evidence been received for the batch?
- Is the payment currently with the beneficiary bank?
- Did a beneficiary bank return it?
- What evidence supports this status?
- What correction or next action is recommended?
- Has this customer or beneficiary had similar prior rejections or returns?

---

## Core Business Statuses

Use these business-facing statuses:

```text
WITH BANK
SENT TO SCHEME
WITH BENEFICIARY BANK
REJECTED BY SCHEME
REJECTED BY BENEFICIARY BANK
```

Do not use `CLEARED` as a payment status in this PoC unless a future artifact provides explicit payment-level clearing evidence.

Do not use `WITH SCHEME` in new UI or backend status models. Use `SENT TO SCHEME`.

Do not use generic `REJECTED` in new business-facing UI. Prefer the specific source:

```text
REJECTED BY SCHEME
REJECTED BY BENEFICIARY BANK
```

Internal sub-statuses are allowed, but they must roll up to the SME-confirmed business statuses above.

Recommended internal sub-statuses:

```text
WITH_BANK_UPLOAD_PENDING
WITH_BANK_SYNTAX_VALIDATION_FAILED
WITH_BANK_SCHEME_REJECT_RECEIVED
SENT_TO_SCHEME_AFTER_BANK_VALIDATION
WITH_BENEFICIARY_BANK_AFTER_SETTLEMENT_SUMMARY
REJECTED_BY_SCHEME_RECORD
REJECTED_BY_BENEFICIARY_BANK_RETURN_FILE
RECONCILIATION_EXCEPTION
REVIEW_REQUIRED
```

---

## Mandatory Status Truth Rules

These rules are mandatory.

### Rule 1 — Settlement Summary Is Not Clearing Evidence

FedACH settlement summary evidence must not be treated as payment-level clearing confirmation.

Do not mark a customer payment as `CLEARED` just because a settlement summary was received.

Settlement summary receipt means:

```text
The batch has moved forward and the related payments are now WITH BENEFICIARY BANK unless rejected by scheme or later returned.
```

### Rule 2 — Every Status Requires Evidence

Every payment status must have an evidence explanation.

Examples:

```text
SENT TO SCHEME
Evidence: CCD file uploaded and bank-side syntax validation passed.

WITH BANK
Evidence: Bank-side syntax validation failed or scheme reject requires bank correction.

WITH BENEFICIARY BANK
Evidence: Settlement summary received for the submitted batch. Settlement is summary-level only; no payment-level clearing is claimed.

REJECTED BY SCHEME
Evidence: Scheme reject file matched this payment or batch.

REJECTED BY BENEFICIARY BANK
Evidence: NACHA return file matched this payment's original trace number.
```

### Rule 3 — Do Not Invent Evidence

Do not invent:

- payment-level settlement results
- cleared trace numbers
- PEP+ behavior
- historical rejection trends
- customer risk history
- NACHA return reasons
- scheme rejection reasons

Only use evidence from uploaded files, demo fixtures, backend state, or deterministic mock data explicitly marked as demo data.

### Rule 4 — Scheme Rejects and Beneficiary Returns Are Different

A scheme rejection means the payment did not successfully move onward and needs bank-side correction.

A beneficiary-bank return means the payment was already sent onward and later returned by the beneficiary bank.

Use different statuses:

```text
REJECTED BY SCHEME
REJECTED BY BENEFICIARY BANK
```

### Rule 5 — Missing Return Is Not Success

If a payment has reached `WITH BENEFICIARY BANK` and no return file has arrived, do not call it successful, cleared, settled, or complete.

Use wording such as:

```text
No return evidence received yet.
Payment remains with beneficiary bank.
```

---

## Key Input Artifacts

The system works with these input artifacts.

### 1. CCD Customer Upload File

The CCD file is a fixed-width ACH file.

Relevant record types:

```text
1 = File Header
5 = Batch Header
6 = Entry Detail
8 = Batch Control
9 = File Control
```

Each type `6` entry detail record becomes one tracked payment.

The parser should eventually extract:

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

```text
10 = Header segment
20 = Summary data segment
30 = Grand trailer / net adjustment segment
```

It is used to determine:

- settlement date
- settlement cycle time
- item count
- settlement category
- gross amount
- net settlement amount

Important limitation:

```text
The settlement report is summary-level evidence only.
It does not identify which customer payments cleared.
```

Therefore:

```text
Settlement summary received => WITH BENEFICIARY BANK
Settlement summary received != CLEARED
```

### 3. Scheme Reject File

The scheme reject file represents records or batches rejected by the ACH scheme.

For this PoC, scheme reject evidence may be represented as mock JSON or sample files.

A scheme reject should include, when available:

- batch ID
- source file name
- rejected trace number if available
- customer ID if available
- amount if available
- scheme reject reason code
- scheme reject reason text
- recommended correction

Scheme reject status:

```text
REJECTED BY SCHEME
```

Operational interpretation:

```text
The payment requires bank-side correction before resubmission.
```

### 4. NACHA Return File

The NACHA return file may contain:

```text
1 = File Header
5 = Batch Header
6 = Returned Entry Detail
7 = Return Addenda
8 = Batch Control
9 = File Control
```

Return addenda record type `7` with addenda type `99` contains:

- return reason code
- original trace number
- date of ODFI return
- original receiving DFI
- return trace number

Return files may arrive in later cycles and must be correlated back to prior payments using the original trace number.

Beneficiary-bank return status:

```text
REJECTED BY BENEFICIARY BANK
```

### 5. Historical Payment Records

Historical payment records are used for early risk identification.

The system should eventually identify:

- similar prior payments
- recent returns
- recurring insufficient-funds patterns
- customer-level rejection trends
- beneficiary-level rejection trends
- prior successful processing patterns

Historical analysis must be evidence-based. The LLM may summarize the trend but must not invent history.

### 6. ACH Processing Engine Evidence

For this PoC, ACH processing-engine evidence may be represented as mock JSON.

Do not assume real PEP+ file formats.

Use generic naming such as “ACH processing engine” unless a demo explicitly labels it as PEP+.

---

## Demo Scenario Behavior

The canonical SME-aligned demo story is:

### 11:00 Cycle

- CCD batch file uploaded.
- 4 payments of $100 each.
- Total CCD amount = $400.
- Bank-side syntax validation passes.
- Payments move to `SENT TO SCHEME`.
- Settlement summary arrives for $300.
- Scheme reject file arrives for $100.

Result:

```text
3 payments move to WITH BENEFICIARY BANK
1 payment moves to REJECTED BY SCHEME
```

Important explanation:

```text
The settlement summary is summary evidence only.
The UI must not claim payment-level clearing from settlement summary.
```

### 11:04 Cycle

- NACHA return file arrives for 1 payment that was previously with beneficiary bank.
- That payment moves to `REJECTED BY BENEFICIARY BANK`.
- Remaining payments stay `WITH BENEFICIARY BANK`.

---

## Demo Mode Requirements

The frontend supports two modes.

### Demo Mode ON

Demo Mode ON means:

```text
Use predefined mocked SME-aligned flow data.
```

Rules:

- Default mode should be ON.
- Show a visible label: `Demo Mode: Mocked SME flow`.
- Use the 11:00 and 11:04 SME-aligned story.
- Do not require backend files.
- Hide or disable local-folder backend controls.
- Do not use `CLEARED` in mock data.
- Every mocked payment status must include evidence.

### Demo Mode OFF

Demo Mode OFF means:

```text
Use backend local-folder demo flow controls.
```

Rules:

- Show a visible label: `Live Folder Mode: Reading backend folder state`.
- Show local-folder controls.
- Use real backend endpoints already implemented under `/api/demo-flow/*`.
- Dashboard mock data may remain visible for presentation, but it must be clearly marked as mocked if it is not backed by parsed ledger data yet.
- Do not imply that file presence equals parsed payment status until parsing is implemented.

---

## Local Folder Demo Flow

The backend local-folder demo flow uses these folders:

```text
backend/demo-inbox/ccd
backend/demo-inbox/settlement
backend/demo-inbox/scheme-reject
backend/demo-inbox/returns
backend/demo-inbox/processed
```

Expected backend endpoints:

```text
GET  /api/demo-flow/config
POST /api/demo-flow/ensure-folders
POST /api/demo-flow/scan-ccd
POST /api/demo-flow/check-settlement
POST /api/demo-flow/check-returns
GET  /api/demo-flow/state
POST /api/demo-flow/reset
```

The UI must call these endpoints only in Live Folder Mode / Demo Mode OFF.

The local folder flow is currently a foundation for file detection and phased demo operation. Do not assume full ACH parsing or payment ledger behavior exists until explicitly implemented.

---

## Sample Local Demo Fixtures

Sample local demo files should live under:

```text
demo-data/local-folder-demo/batch_1100/
```

Suggested structure:

```text
demo-data/local-folder-demo/batch_1100/ccd/batch_1100.ach
demo-data/local-folder-demo/batch_1100/settlement/batch_1100_settlement.dat
demo-data/local-folder-demo/batch_1100/scheme-reject/batch_1100_reject.json
demo-data/local-folder-demo/batch_1100/returns/batch_1100_return.ach
```

Runtime files are copied into:

```text
backend/demo-inbox/ccd
backend/demo-inbox/settlement
backend/demo-inbox/scheme-reject
backend/demo-inbox/returns
```

Do not confuse source fixtures with runtime folders.

---

## Batch Cycle Requirements

The real-world batch cycles may include times such as:

```text
10:00 GMT
14:00 GMT
18:00 GMT
```

The demo must also support accelerated configurable cycles, such as:

```text
11:00
11:04
11:08
```

Do not hard-code the system to only 10:00, 14:00, and 18:00.

The simulator should support:

- realistic day schedule
- accelerated demo schedule
- manually configured cycle times
- run-next-cycle mode without waiting for real time

---

## Agent Architecture

Build the solution as a multi-agent workflow over time.

### 1. BeforePaymentSubmissionAgent

Responsibilities:

- Parse CCD file.
- Run syntax validation.
- Create payment records.
- Stamp initial status as `WITH BANK` during validation.
- Move valid payments to `SENT TO SCHEME`.
- Run historical similarity analysis.
- Flag recent or recurring rejection risk.
- Identify syntax errors.
- Provide correction guidance before submission.

Output should include:

- validation status
- syntax findings
- historical-risk findings
- payment records created
- recommended user action
- evidence references

### 2. SchemeAndSettlementAgent

Responsibilities:

- Consume ACH processing-engine or scheme evidence.
- Update valid submitted payments to `SENT TO SCHEME`.
- Read scheme reject evidence.
- Mark scheme-rejected payments as `REJECTED BY SCHEME`.
- Read FedACH settlement summary evidence.
- Move non-rejected submitted payments to `WITH BENEFICIARY BANK`.
- Clearly state settlement-summary limitations.
- Do not mark individual payments as `CLEARED` from summary settlement.

Output should include:

- scheme submission status
- scheme rejection findings
- settlement summary
- payment movement to beneficiary-bank stage
- reconciliation limitations
- status updates applied
- evidence references

### 3. ReturnFileAgent

Responsibilities:

- Parse NACHA return file.
- Extract return reason code.
- Extract original trace number.
- Link return back to original payment.
- Mark matched payment as `REJECTED BY BENEFICIARY BANK`.
- Produce root cause and customer-safe corrective guidance.
- Identify recurring rejection trend if historical evidence exists.

Output should include:

- return records parsed
- original payments matched
- unmatched returns
- beneficiary-bank rejection status updates
- customer-friendly message
- recommended action
- evidence references

### 4. PaymentLifecycleOrchestrator

Responsibilities:

- Run the lifecycle across configured demo cycles.
- Maintain the payment status ledger.
- Coordinate submission, settlement, scheme rejection, and return processing.
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
- Clearly distinguish deterministic status from AI interpretation.

---

## Payment Status Ledger

The status ledger is central to the future system.

Every CCD type `6` entry should become a payment tracking record.

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
- scheme rejection reason if applicable
- return reason code if applicable
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

### 1. Demo Simulator View

Purpose:

Run and visualize configurable ACH batch cycles.

Must include:

- scenario selector
- cycle schedule configuration
- current simulated time
- current active cycle
- Demo Mode toggle
- run next cycle
- reset
- event log or timeline
- status summary cards
- agent trace panel
- local-folder controls when Demo Mode is OFF

### 2. Batch Dashboard

Purpose:

Show payments by batch.

Filters may include:

- batch ID
- cycle time
- file name
- date
- status
- return code

Columns may include:

- batch ID
- cycle time
- payment ID / trace number
- customer ID
- customer name
- beneficiary name
- amount
- current status
- risk flag
- scheme reject reason
- return code
- last event
- recommended action

### 3. Customer Dashboard

Purpose:

Show all payments for a customer across batches and dates.

Filters may include:

- customer ID
- customer name
- beneficiary name
- date range
- status
- return code

Columns may include:

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
- bank-validation evidence
- scheme-reject evidence
- settlement-summary evidence
- return-file evidence
- historical-risk evidence
- agent trace
- customer-friendly explanation
- next-best action
- evidence limitations

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
```

Do not add new frontend dependencies unless explicitly requested.

The frontend should clearly label whether data is:

```text
Mocked SME demo data
```

or

```text
Live backend folder state
```

Do not allow UI wording to imply that mocked data is parsed production data.

---

## Backend Technical Requirements

Use:

- Python
- FastAPI
- Pydantic
- pytest

Backend location:

```text
backend/
```

Backend package import path:

```text
payment_tracking_agent
```

Do not add heavy new dependencies unless explicitly requested.

Prefer deterministic services and tests before adding LLM behavior.

---

## LLM / AI Requirements

LLM features are allowed only where explicitly requested.

The LLM may:

- explain syntax findings
- summarize scheme rejection reasons
- summarize NACHA return reasons
- suggest correction steps
- generate customer-safe explanations
- summarize historical patterns from provided evidence

The LLM must not:

- invent payment statuses
- invent payment clearing
- invent customer history
- invent scheme behavior
- invent NACHA return reasons
- override deterministic evidence

Every AI explanation must be grounded in evidence.

Use wording such as:

```text
Based on the available evidence...
```

or:

```text
No payment-level clearing evidence is available from the settlement summary.
```

---

## Coding Rules

When implementing code:

1. Read this file before editing.
2. Keep changes scoped to the prompt.
3. Do not modify backend files during frontend-only prompts.
4. Do not modify frontend source during backend-only prompts.
5. Do not add new dependencies unless explicitly requested.
6. Do not commit changes unless explicitly requested.
7. Preserve existing working commands.
8. Keep code simple and demoable.
9. Prefer typed models over loose dictionaries.
10. Add or update tests for backend behavior.
11. Run validation commands requested by the prompt.
12. Do not silently change business status semantics.

---

## Forbidden Old Assumptions

Do not reintroduce these old assumptions:

```text
Settlement confirms cleared payments.
18 payments cleared from settlement.
12 payments cleared from settlement.
CLEARED_BY_SETTLEMENT.
WITH SCHEME as a business-facing status.
Generic REJECTED as a business-facing status.
Payments not in settlement are failed.
Missing return means success.
```

Use instead:

```text
Settlement summary received.
Moved to beneficiary bank.
No payment-level clearing is claimed from settlement summary.
Scheme reject received.
Return file matched original trace.
Rejected by scheme.
Rejected by beneficiary bank.
```

---

## Current Implementation Milestones

The project currently has:

- Full-stack skeleton.
- Backend health endpoint.
- Frontend React/Vite app.
- Mocked dashboard UI.
- Backend local-folder demo flow.
- Demo inbox folders.
- Demo Mode toggle.
- SME-aligned mocked demo flow.
- Live Folder Mode controls that call backend `/api/demo-flow/*` endpoints.

The project does not yet have full production-grade:

- ACH CCD parser
- FedACH settlement parser
- NACHA return parser
- payment ledger
- LLM explanation service
- authentication
- database persistence

Do not imply those features exist until implemented.

---

## Validation Expectations

Frontend validation:

```powershell
cd frontend
npm run build
```

Backend validation:

```powershell
cd backend
python -m pytest
```

Generated build metadata such as the following should not be committed:

```text
frontend/tsconfig.tsbuildinfo
```

---

## Commit Hygiene

Before committing:

```powershell
git status
```

Do not commit generated build artifacts.

Prefer focused commit messages such as:

```text
feat(frontend): add demo mode toggle with SME-aligned flow
feat(backend): add local folder demo seed fixtures
docs: align copilot instructions with SME-confirmed ACH flow
```