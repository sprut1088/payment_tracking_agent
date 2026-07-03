# Prompt 15 — Final Demo QA Checklist and Small UX Fixes

Read `.github/copilot-instructions.md` before editing.

Frontend and documentation only unless a tiny non-business backend fix is absolutely required.

## Objective

Run a final end-to-end demo QA pass and apply only small UX/documentation fixes.

Do not add major features.

The current application already supports:

- Demo Mode ON mocked SME-aligned story
- Demo Mode OFF live folder-driven flow
- CCD parsing into live ledger
- settlement summary evidence
- scheme reject evidence
- NACHA return evidence
- live Batch Dashboard
- live Customer Dashboard
- live Payment Search with detail, status history, and evidence
- UI runbook
- README runbook

This prompt should make the demo easier, clearer, and safer to present.

## Required QA Checklist

Review the app manually in both modes.

### Demo Mode ON

Verify:

- Mocked scripted story still works.
- No backend files are required.
- UI clearly says this is a scripted SME-aligned mock story.
- No `CLEARED` status is shown in dashboards.
- Settlement summary is not described as payment-level clearing evidence.

### Demo Mode OFF

Verify:

- Demo Simulator shows the Live Folder Demo Runbook.
- Local Folder Demo Flow controls still work.
- Live Payment Ledger is visible after CCD scan.
- Batch Dashboard uses live ledger data.
- Customer Dashboard uses live ledger data.
- Payment Search uses live ledger data.
- Payment detail shows status history and evidence.
- Empty states guide the user to Demo Simulator and Scan CCD.
- No UI copy says payment was cleared.

## Required Small UX Fixes

Apply small fixes only if needed.

Suggested acceptable fixes:

1. Make long evidence text wrap cleanly in tables and detail cards.
2. Make table columns readable at 1440px and 1920px widths.
3. Make status summary chips align consistently.
4. Make runbook commands easier to copy/read.
5. Add short helper text where users might be confused.
6. Improve empty states.
7. Ensure `Refresh ledger` buttons are consistently placed.
8. Ensure Live Mode labels are consistent across pages.
9. Ensure Demo Mode ON/OFF copy is consistent.
10. Remove stale or misleading wording.

## Required Final Demo Script

Update root `README.md` with a concise section:

```text
Final Demo Script
```


## Include:

Start backend.
Start frontend.
Use Demo Mode ON to show scripted mock flow.
Switch Demo Mode OFF.
Run clean seed command.
Run CCD seed command and click Scan CCD.
Show Live Payment Ledger with SENT TO SCHEME.
Run settlement seed command and click Check settlement.
Show WITH BENEFICIARY BANK and REJECTED BY SCHEME.
Run returns seed command and click Check returns.

Show final counts:
14 WITH BENEFICIARY BANK
1 REJECTED BY SCHEME
1 REJECTED BY BENEFICIARY BANK
0 CLEARED
Open Batch Dashboard, Customer Dashboard, and Payment Search.
Open one scheme rejected payment and one beneficiary-bank rejected payment.
Emphasize:
Settlement summary is summary-level evidence only. The demo does not mark individual payments as cleared from settlement summary.

## Hard Rules

Do not change backend business logic.
Do not change parser behavior.
Do not change ledger status transition behavior.
Do not add new dependencies.
Do not add authentication.
Do not add LLM calls.
Do not remove Demo Mode ON mocked story.
Do not use CLEARED as a payment status.

The README may mention 0 CLEARED only as an explicit final-demo count showing no payment is marked cleared.

Files Likely To Change

Frontend files may include:

frontend/src/components/LiveBatchDashboard.tsx
frontend/src/components/LiveCustomerDashboard.tsx
frontend/src/components/LivePaymentSearch.tsx
frontend/src/components/LiveFolderRunbook.tsx
frontend/src/components/LocalFolderDemoControls.tsx
frontend/src/pages/DemoSimulatorPage.tsx
frontend/src/styles/app.css

Documentation may include:

README.md

Only update other frontend/docs files if necessary.

## Validation

After implementation, run:

cd frontend
npm run build

If backend files were accidentally changed, revert them before finishing.

Backend tests are optional for this prompt unless backend files changed.

## Expected Summary

Summarize:

files changed
small UX fixes made
README Final Demo Script added
confirmation that backend business logic was not changed
confirmation that Demo Mode ON still exists
validation result