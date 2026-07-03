# ACH Payment Tracking Agent

## Purpose

ACH Payment Tracking Agent is a full-stack demo application for tracking ACH payments across CCD batch upload, bank-side validation, scheme submission, settlement summary receipt, beneficiary-bank processing, delayed NACHA return files, and AI-assisted investigation.

The business goal is to help bank operations users answer:

> Where is this customer's ACH payment right now?

The application tracks payment status at individual trace-number level while also supporting batch, customer, date, and payment-detail views.

---

## Business Problem

ACH payment processing is batch-based and asynchronous.

A bank user uploads a CCD batch file containing individual payment records and trace numbers. The bank performs syntax validation during upload. If validation passes, the payment records are submitted to the scheme through the bank's ACH processing flow. The scheme may perform its own validations. If scheme validation fails, the records come back to the bank for correction.

If scheme validation succeeds, the scheme sends the payments onward to the beneficiary bank. A FedACH settlement report or settlement summary may be received by the initiator bank, but the SME-confirmed settlement file is summary-level. It does not necessarily contain individual customer payment records or original trace numbers.

Therefore, settlement summary receipt should not be treated as proof that individual customer payments are cleared.

After settlement summary is received, payments in the submitted batch should be shown as:

`WITH BENEFICIARY BANK`

Later, the beneficiary bank may send a NACHA return file in a later batch cycle, later in the day, next day, next week, or another future cycle. The return file contains item-level return information including original trace number and return reason code. When a return is received and matched, the payment should be marked as:

`REJECTED BY BENEFICIARY BANK`

---

## SME-Confirmed Payment Flow

### 1. CCD Batch Upload

A bank user uploads a CCD batch file containing individual payment trace numbers.

Bank-side syntax validation is performed at upload.

If syntax validation passes, payments move to:

`SENT TO SCHEME`

If syntax validation fails, but payment traces and customer details can still be classified, those payments remain:

`WITH BANK`

Example syntax issues:

- missing file control record,
- invalid record length,
- invalid record sequence,
- invalid batch total,
- invalid file total,
- missing required header/control records.

The AI agent should explain the syntax issue and recommend how to correct it.

---

### 2. Scheme Validation

After successful bank-side validation, the file is sent to the scheme.

The scheme may perform additional validations. If the scheme rejects the batch or records, those records come back to the bank for correction.

Primary stage:

`WITH BANK`

Secondary status:

`REJECTED BY SCHEME`

The AI agent should explain the scheme rejection reason and provide a precise correction recommendation.

---

### 3. Settlement Summary Receipt

If scheme validation passes, the scheme sends the payment file to the beneficiary bank.

The scheme sends a FedACH settlement file or settlement summary back to the initiator bank.

The SME-confirmed settlement file is summary-level. It may show total transactions, total amount, settlement category, sort code, settlement window, or net settlement amount. It does not provide individual customer payment status.

When settlement summary is received, all payments in the submitted batch move to:

`WITH BENEFICIARY BANK`

Important rule:

> Do not mark individual customer payments as cleared from summary-only settlement files.

---

### 4. Beneficiary Bank Return

The beneficiary bank can return a payment later.

The return may arrive:

- later in the day,
- in the next run,
- next day,
- next week,
- or at any later supported return cycle.

The NACHA return file contains item-level return information, including original trace number and return reason code.

The system should match:

`return.original_trace_number`

to:

`ccd.entry.trace_number`

When a match is found, the payment moves to:

`REJECTED BY BENEFICIARY BANK`

---

## Core Payment Stages

| Stage | Meaning |
|---|---|
| `WITH BANK` | Payment is still with the bank because upload failed, bank-side syntax validation failed, correction is needed, or scheme rejected it. |
| `SENT TO SCHEME` | Payment passed bank-side validation and was submitted to the scheme. |
| `WITH BENEFICIARY BANK` | Settlement summary was received and the payment is considered to be with the beneficiary bank pending any future return. |
| `REJECTED BY BENEFICIARY BANK` | NACHA return file was received and matched to the original payment trace number. |

Secondary statuses include `SYNTAX_VALIDATION_FAILED`, `REJECTED_BY_SCHEME`, `SETTLEMENT_SUMMARY_RECEIVED`, `AWAITING_RETURN_OR_COMPLETION`, `RETURNED_R01_INSUFFICIENT_FUNDS`, and `RETURNED_OTHER`.

---

## AI / Agentic Capabilities

The AI and agentic layer assists at each stage but does not invent payment status.

### Before Submission

The AI should:

- read the CCD upload file,
- identify syntax issues,
- explain why the file failed,
- provide correction recommendations,
- analyze historical rejection patterns,
- flag customers or beneficiaries recently rejected by beneficiary banks,
- calculate risk level and confidence.

### Scheme Rejection

The AI should:

- read scheme rejection evidence,
- explain the rejection reason,
- identify likely root cause,
- provide correction recommendation,
- update the payment ledger.

### Beneficiary Return

The AI should:

- read NACHA return files,
- understand return reason codes,
- match returns back to original trace numbers,
- explain return reasons in customer-friendly language,
- recommend next action,
- update memory for future risk scoring.

---

## AI Memory Requirement

The platform must maintain an operational memory of:

- successful processing,
- syntax failures,
- scheme rejections,
- beneficiary-bank returns,
- customer-level rejection patterns,
- beneficiary-level rejection patterns,
- repeated return reason codes,
- prior recommendations,
- risk scores,
- confidence trends.

This memory should support proactive risk scoring before future submissions.

Example:

> This beneficiary had two recent R01 insufficient-funds returns. Flag this payment as high risk before submission.

---

## Architecture

```text
frontend/
  React + TypeScript + Vite demo UI

backend/
  Python API and ACH processing engine

demo-data/
  Sample CCD, settlement, return, history, and scenario files

docs/
  Business and technical documentation
```

---

## Agent Architecture

### BeforePaymentSubmissionAgent

Responsible for CCD parsing, syntax validation, payment trace extraction, customer extraction, historical risk analysis, correction recommendation, and initial status assignment.

### SchemeValidationAgent

Responsible for reading scheme rejection evidence, classifying scheme rejection, moving rejected records back to `WITH BANK`, and generating correction recommendations.

### AfterSettlementAgent

Responsible for reading settlement summary, confirming scheme-to-beneficiary-bank progression, moving submitted payments to `WITH BENEFICIARY BANK`, and not claiming item-level clearing from summary-only settlement.

### ReturnFileAgent

Responsible for parsing NACHA return files, extracting original trace number and return reason code, matching returns to original CCD entries, and marking matched payments as `REJECTED BY BENEFICIARY BANK`.

### AIExplanationAgent

Responsible for explaining deterministic evidence, summarizing risk, creating customer-safe wording, recommending next action, and maintaining grounded responses.

### PaymentLifecycleOrchestrator

Responsible for running agents across configurable cycles, updating the payment ledger, and supporting dashboard views by batch, customer, date, and payment.

---

## Demo Cycle Requirement

The real-world batch process may run at times such as:

- 10:00 GMT,
- 14:00 GMT,
- 18:00 GMT.

The demo must support accelerated configurable cycles, such as:

- 10:00,
- 10:02,
- 10:04,
- 10:06.

The user should be able to run the next cycle manually from the UI.

---

## Current Project Status

Completed:

- full-stack skeleton,
- backend smoke test,
- frontend Vite build,
- initial demo UI shell with mocked data.

Next planned build steps:

1. Align documentation and Copilot instructions with SME-confirmed flow.
2. Build backend demo scenario loader.
3. Build payment status ledger.
4. Build CCD parser and upload validation.
5. Build scheme rejection artifact support.
6. Build settlement summary ingestion.
7. Build NACHA return matching.
8. Add AI memory and risk scoring.
9. Connect frontend to backend APIs.
10. Add LLM explanation layer.

---

## Backend Commands

```powershell
cd backend
python -m pip install -e .
python -m pytest
python -m uvicorn payment_tracking_agent.main:app --reload --port 8000
```

---

## Frontend Commands

```powershell
cd frontend
npm install
npm run build
npm run dev
```

---

## Local Folder Demo File Seeding

```powershell
.\scripts\seed-local-demo-files.ps1 -Phase clean
.\scripts\seed-local-demo-files.ps1 -Phase ccd
.\scripts\seed-local-demo-files.ps1 -Phase settlement
.\scripts\seed-local-demo-files.ps1 -Phase returns
```

- after ccd, click Scan CCD
- after settlement, click Check settlement
- after returns, click Check returns

---

## End-to-End Demo Runbook

The app has two demo modes. Use the top-right Demo Mode toggle to switch.

### Demo Mode ON

- Use for scripted presentation.
- No backend files required.
- Shows the SME-aligned mocked flow (11:00 and 11:04 cycles).
- Dashboards and Payment Search use scripted mock records only.

### Demo Mode OFF

Use to drive the live backend ledger from parsed CCD, settlement, scheme-reject, and NACHA return files.

Start the backend and frontend in separate terminals:

```powershell
cd C:\git_repos\payment_tracking_agent\backend
python -m uvicorn payment_tracking_agent.main:app --reload --port 8000
```

```powershell
cd C:\git_repos\payment_tracking_agent\frontend
npm run dev
```

Then run the seeding sequence from the repo root:

```powershell
cd C:\git_repos\payment_tracking_agent

.\scripts\seed-local-demo-files.ps1 -Phase clean

.\scripts\seed-local-demo-files.ps1 -Phase ccd
# Click Scan CCD in the Demo Simulator page

.\scripts\seed-local-demo-files.ps1 -Phase settlement
# Click Check settlement in the Demo Simulator page

.\scripts\seed-local-demo-files.ps1 -Phase returns
# Click Check returns in the Demo Simulator page
```

Open Batch Dashboard, Customer Dashboard, or Payment Search to inspect the live ledger. Each live view is labeled `Live backend ledger from parsed CCD and file evidence`.

### Expected Final Ledger Counts

After the four-phase seeding sequence completes, the live payment ledger should report:

- 14 `WITH BENEFICIARY BANK`
- 1 `REJECTED BY SCHEME`
- 1 `REJECTED BY BENEFICIARY BANK`
- 0 `CLEARED`

FedACH settlement summary is summary-level evidence only. The demo does not mark individual payments as cleared from settlement summary.

---

## Important Design Rule

Do not mark individual customer payments as cleared using summary-only settlement files.

Settlement summary should move payments to:

`WITH BENEFICIARY BANK`

Only explicit item-level evidence or return evidence should update individual payment outcomes beyond that stage.
