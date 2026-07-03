# Prompt 12 — Frontend Live Ledger Integration

Read `.github/copilot-instructions.md` before editing.

Frontend only.

## Objective

In Demo Mode OFF / Live Folder Mode, show the real backend payment ledger returned by:

```text
GET /api/demo-flow/payments
```

Demo Mode ON must continue showing mocked SME-aligned dashboard data.
Demo Mode OFF should now show real parsed CCD/payment-status data created by the backend file-driven flow.

## Current Backend Flow

The backend now supports this real file-driven ledger flow:

POST /api/demo-flow/scan-ccd
Parses CCD type 6 records.
Creates real in-memory payment ledger records.
Initial status: SENT TO SCHEME.
POST /api/demo-flow/check-settlement
Applies settlement summary evidence.
Applies scheme-reject evidence.
Moves non-rejected payments to WITH BENEFICIARY BANK.
Moves matched scheme-reject trace to REJECTED BY SCHEME.
Does not mark anything CLEARED.
POST /api/demo-flow/check-returns
Applies NACHA return evidence.
Moves matched return trace to REJECTED BY BENEFICIARY BANK.
Does not overwrite REJECTED BY SCHEME.
GET /api/demo-flow/payments
Returns the current in-memory payment ledger.

## Expected sample final status counts after the full seeded flow:

14 WITH BENEFICIARY BANK
1 REJECTED BY SCHEME
1 REJECTED BY BENEFICIARY BANK
0 CLEARED
API Shape

## Add frontend types for the backend response.

Expected response shape:

{
  as_of: string;
  payments: Array<{
    payment_id: string;
    batch_key: string;
    source_file: string;
    trace_number: string;
    transaction_code: string;
    receiving_dfi_identification: string;
    masked_account_number: string;
    amount_cents: number;
    individual_id_number: string;
    individual_name: string;
    current_status: "WITH BANK" | "SENT TO SCHEME" | "WITH BENEFICIARY BANK" | "REJECTED BY SCHEME" | "REJECTED BY BENEFICIARY BANK";
    status_history: Array<{
      status: string;
      at: string;
      evidence: {
        source: string;
        summary: string;
        recorded_at: string;
      };
    }>;
    evidence: Array<{
      source: string;
      summary: string;
      recorded_at: string;
    }>;
  }>;
}


## Required UI Behavior

In Demo Mode OFF:

The Local Folder Demo Flow panel should fetch and display the live payment ledger.
Add or reuse a section titled:
Live Payment Ledger
Show a clear label:
Live backend ledger from parsed CCD and file evidence
Show status summary counts from real backend ledger data.
Show a table with at least:
Payment ID
Trace Number
Customer / Individual Name
Customer / Individual ID
Amount
Current Status
Latest Evidence
Amount should display dollars from amount_cents.
Current Status should use existing StatusBadge.
Latest Evidence should show the latest evidence summary or status-history evidence summary.
If there are no ledger payments yet, show:
No live ledger payments yet. Seed CCD files, then click Scan CCD.
Add a Refresh payments button.
After each live folder action, refresh payments automatically:
Ensure folders
Scan CCD
Check settlement
Check returns
Reset
After Reset, the live payment ledger should clear or refresh to empty.

## Demo Mode Behavior

Demo Mode ON:

Keep using mocked SME-aligned demo data.
Do not call /api/demo-flow/payments unless needed for shared code.
Do not replace mocked dashboards.

Demo Mode OFF:

Show Local Folder Demo Flow controls.
Show Live Payment Ledger from backend.
Clearly distinguish this from mocked dashboard data.

## Important Wording Rules

Do not use CLEARED.
Do not say settlement means payment cleared.

Use wording like:

Settlement summary evidence received
Moved to beneficiary bank
Scheme reject matched trace
Return file matched original trace
No payment-level clearing is claimed from settlement summary
Files Likely To Change

Frontend files may include:

frontend/src/api/client.ts
frontend/src/types/api.ts
frontend/src/components/LocalFolderDemoControls.tsx
frontend/src/components/StatusBadge.tsx
frontend/src/styles/app.css

Only update other frontend files if necessary.

## Do Not Do

Do not modify backend files.
Do not modify backend tests.
Do not implement backend parsing.
Do not add LLM calls.
Do not add authentication.
Do not add dependencies.
Do not change Demo Mode ON mocked story.
Do not commit.

## Validation

After implementation, this must pass:

cd frontend
npm run buil

## Expected Summary

Summarize:

files changed
API client/types added
Live Payment Ledger behavior
Demo Mode ON preserved
validation result