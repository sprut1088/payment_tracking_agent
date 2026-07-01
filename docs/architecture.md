# Architecture

High-level architecture of the ACH Payment Tracking Agent. This is a
placeholder authored during bootstrap and expanded in later prompts.

## Components

- **Backend** (Python, FastAPI) — hosts agents, ledger, simulator, REST API.
- **Frontend** (React, TypeScript, Vite) — demo UI with simulator, batch,
  customer, and payment-detail views.
- **Demo data** — CCD, settlement, return, and historical fixtures.
- **Prompts** — ordered build prompts under `.github/prompts/`.

## Data flow

1. CCD file uploaded to backend.
2. `BeforePaymentSubmissionAgent` validates, creates payment records, and
   flags historical risk. Status: `WITH BANK`.
3. Processing-engine (PEP+) evidence advances payments to `WITH SCHEME`.
4. Settlement evidence advances cleared payments to `CLEARED` and holds the
   rest at `WITH BENEFICIARY BANK`.
5. NACHA return files, arriving in the same or later cycle, transition
   matched payments to `REJECTED`.
6. `AIExplanationAgent` produces customer-safe explanations grounded in
   evidence.

## Ledger

The payment status ledger is the source of truth. Every status transition
carries an evidence reference and appears on the payment's status timeline.
