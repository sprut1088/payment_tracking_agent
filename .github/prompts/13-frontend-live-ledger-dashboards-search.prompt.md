# Prompt 13 — Frontend Live Ledger Dashboards and Search

Read `.github/copilot-instructions.md` before editing.

Frontend only.

## Objective

Extend Demo Mode OFF / Live Folder Mode so the main dashboard pages use the real backend payment ledger from:

```text
GET /api/demo-flow/payments
```

Demo Mode ON must continue using mocked SME-aligned demo data.

## Current State

The Local Folder Demo Flow panel already shows the live payment ledger in Demo Mode OFF.

Now update these pages so they are mode-aware:

Batch Dashboard
Customer Dashboard
Payment Search / Payment Detail

## Required Behavior

Demo Mode ON

When Demo Mode is ON:

Keep existing mocked SME-aligned demo data.
Do not replace the scripted mock dashboard story.
Do not call the live ledger endpoint unless existing shared code requires it.
Continue showing the presentation-safe mocked flow.
Demo Mode OFF

When Demo Mode is OFF:

Use real backend ledger data from /api/demo-flow/payments.
Clearly label pages as:
Live backend ledger from parsed CCD and file evidence
If no payments exist yet, show:
No live ledger payments yet. Go to Demo Simulator, seed CCD files, then click Scan CCD.
Add a Refresh ledger button where useful.
Use existing StatusBadge for statuses.
Do not show or imply CLEARED.


## Batch Dashboard Requirements

In Demo Mode OFF, the Batch Dashboard should:

Group live payments by batch_key.
Show summary cards/counts by current status.
Show a table with:
Batch Key
Payment ID
Trace Number
Individual Name
Individual ID
Amount
Current Status
Latest Evidence
Amount should display dollars from amount_cents.

## Customer Dashboard Requirements

In Demo Mode OFF, the Customer Dashboard should:

Group live payments by individual_id_number and individual_name.
Show customer-level counts by status.
Show a table with:
Individual ID
Individual Name
Payment ID
Trace Number
Batch Key
Amount
Current Status
Latest Evidence

## Payment Search Requirements

In Demo Mode OFF, Payment Search should:

Search live ledger payments by:
payment_id
trace_number
individual_id_number
individual_name
batch_key
Show matching payments.
Selecting a payment should show details including:
Payment ID
Batch Key
Source File
Trace Number
Individual ID
Individual Name
Masked Account Number
Amount
Current Status
Status History
Evidence
Status history should show each status, timestamp, and evidence summary.

## Important Wording Rules

Do not use:

CLEARED
cleared
settlement confirmed payment

Use wording such as:

Settlement summary evidence received
Moved to beneficiary bank
Scheme reject matched trace
Return file matched original trace
No payment-level clearing is claimed from settlement summary

## Implementation Guidance

Create shared frontend helpers if useful, such as:

fetch live ledger
format amount
get latest evidence
group payments by batch
group payments by individual

Only add helpers if they keep the code simple.

## Files Likely To Change

Frontend files may include:

frontend/src/App.tsx
frontend/src/api/client.ts
frontend/src/types/api.ts
frontend/src/pages/BatchDashboardPage.tsx
frontend/src/pages/CustomerDashboardPage.tsx
frontend/src/pages/PaymentSearchPage.tsx
frontend/src/components/BatchDashboard.tsx
frontend/src/components/CustomerDashboard.tsx
frontend/src/components/PaymentDetailDrawer.tsx
frontend/src/components/StatusBadge.tsx
frontend/src/styles/app.css

Only update other frontend files if necessary.

## Do Not Do

Do not modify backend files.
Do not modify backend tests.
Do not change backend API behavior.
Do not implement new parsing.
Do not add LLM calls.
Do not add authentication.
Do not add dependencies.
Do not remove Demo Mode ON mocked story.
Do not commit.

## Validation

After implementation, this must pass:

cd frontend
npm run build

## Expected Summary

Summarize:

files changed
how Batch Dashboard behaves in Demo Mode OFF
how Customer Dashboard behaves in Demo Mode OFF
how Payment Search behaves in Demo Mode OFF
confirmation that Demo Mode ON mocked story is preserved
validation result