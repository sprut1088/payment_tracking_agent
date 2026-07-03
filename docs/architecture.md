# Architecture

This document describes the high-level architecture of the ACH Payment Tracking Agent.

The system is a full-stack demo application that tracks ACH payment stages across CCD upload, bank-side validation, scheme submission, settlement summary receipt, beneficiary-bank processing, NACHA returns, and AI-assisted investigation.

---

## Components

- **Frontend** — React, TypeScript, and Vite demo UI with simulator, batch dashboard, customer dashboard, and payment-detail views.
- **Backend** — Python API and ACH processing engine responsible for parsing, validation, status ledger updates, orchestration, and explanation APIs.
- **Demo data** — CCD upload files, settlement summary files, return files, historical memory fixtures, scheme rejection samples, and scenario manifests.
- **Payment status ledger** — Source of truth for every trace-number-level payment record and status transition.
- **Agent layer** — Deterministic agents plus AI explanation layer.
- **AI memory layer** — Stores prior successful processing, syntax failures, scheme rejections, return reasons, and customer/beneficiary risk trends.

---

## Confirmed Data Flow

### 1. CCD Upload

A CCD file is uploaded by the bank user. The file contains individual payment records and trace numbers.

The backend parses the CCD file and creates one payment ledger record for each payment entry that can be classified.

If upload syntax validation fails, but payment traces and customer details can still be parsed, those payments remain at:

`WITH BANK`

The ledger stores the syntax issue as evidence.

---

### 2. Bank-Side Validation Passed

If bank-side syntax validation passes, the payments are submitted to the scheme.

The payments move to:

`SENT TO SCHEME`

The ledger records the CCD upload and validation event as evidence.

---

### 3. Scheme Validation

The scheme may reject the file or records due to scheme-level validation issues.

If scheme rejection evidence is received, affected payments move to:

Primary stage:

`WITH BANK`

Secondary status:

`REJECTED BY SCHEME`

The ledger records the scheme rejection artifact and AI correction recommendation.

---

### 4. Settlement Summary Receipt

If scheme validation passes, the scheme sends the batch onward to the beneficiary bank and sends a settlement summary to the initiator bank.

The SME confirmed that the FedACH settlement file used here is summary-level. It does not identify individual customer payment records.

Therefore, settlement summary receipt moves submitted payments to:

`WITH BENEFICIARY BANK`

It does not move individual payments to `CLEARED`.

---

### 5. Beneficiary Bank Return

The beneficiary bank can send a NACHA return file later.

The return file contains item-level return information including original trace number and return reason code.

The backend matches:

`return.original_trace_number`

to:

`ccd.entry.trace_number`

Matched payments move to:

`REJECTED BY BENEFICIARY BANK`

---

## Payment Status Ledger

The payment status ledger is the source of truth.

Every ledger record should include:

- payment tracking ID,
- original trace number,
- batch ID,
- source file name,
- upload cycle,
- company ID,
- customer ID if available,
- customer name if available,
- beneficiary name,
- receiving DFI,
- masked account number,
- amount,
- current primary stage,
- current secondary status,
- status history,
- evidence references,
- risk score,
- confidence score,
- AI recommendation.

Every status transition must include:

- timestamp,
- previous stage,
- new stage,
- source artifact,
- source agent,
- evidence summary,
- confidence.

---

## Agent Execution Model

The lifecycle orchestrator coordinates these agents:

1. `BeforePaymentSubmissionAgent`
2. `SchemeValidationAgent`
3. `AfterSettlementAgent`
4. `ReturnFileAgent`
5. `AIExplanationAgent`

Agents must update the ledger using evidence-backed transitions only.

---

## Backend API Direction

The backend should eventually expose APIs for:

- health check,
- scenario listing,
- simulation state,
- run next cycle,
- batch dashboard,
- customer dashboard,
- payment search,
- payment detail,
- AI explanation.

---

## Frontend Direction

The frontend should show:

- configurable cycle simulator,
- payment status summary,
- batch dashboard,
- customer dashboard,
- payment search,
- payment detail evidence,
- agent trace,
- AI explanation.

The frontend must not duplicate ACH business logic. It should display backend-computed ledger state.

---

## Critical Architecture Rule

Settlement summary is not individual clearing evidence.

It should move payments to:

`WITH BENEFICIARY BANK`

not:

`CLEARED`

unless a future item-level clearing artifact is explicitly provided.
