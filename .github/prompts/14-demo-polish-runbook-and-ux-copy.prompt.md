# Prompt 14 — Demo Polish, Runbook, and UX Copy

Read `.github/copilot-instructions.md` before editing.

Frontend and documentation only.

## Objective

Polish the application so it is easy to demo end-to-end.

The app already supports:

- Demo Mode ON mocked SME-aligned story
- Demo Mode OFF live folder-driven ledger
- CCD parsing
- settlement summary evidence
- scheme reject evidence
- NACHA return evidence
- live dashboards and payment search

This prompt should improve UX copy, demo instructions, and documentation without changing backend business logic.

## Required UX Improvements

### 1. Demo Simulator Page

In Demo Mode OFF, add a short numbered runbook near the Local Folder Demo Flow panel.

Title:

```text
Live Folder Demo Runbook
```


## Below are Steps for reference:

1. Run the seed script with -Phase clean.
2. Run the seed script with -Phase ccd, then click Scan CCD.
3. Run the seed script with -Phase settlement, then click Check settlement.
4. Run the seed script with -Phase returns, then click Check returns.
5. Open Batch Dashboard, Customer Dashboard, or Payment Search to inspect the live ledger.

Include exact PowerShell commands:

.\scripts\seed-local-demo-files.ps1 -Phase clean
.\scripts\seed-local-demo-files.ps1 -Phase ccd
.\scripts\seed-local-demo-files.ps1 -Phase settlement
.\scripts\seed-local-demo-files.ps1 -Phase returns

## 2. Live Ledger UX Copy

Make sure all Live Folder Mode sections clearly say:

Live backend ledger from parsed CCD and file evidence.
Settlement summary is not payment-level clearing evidence.

Do not use CLEARED.

Do not say payment was cleared.

## 3. Demo Mode ON Copy

Make sure Demo Mode ON clearly says:

Demo Mode ON: scripted SME-aligned mock story.

Do not imply mock data came from parsed files.

## 4. Empty States

Improve empty states across live pages:

Live Payment Ledger
Live Batch Dashboard
Live Customer Dashboard
Live Payment Search

Use this wording:

No live ledger payments yet. Go to Demo Simulator, switch Demo Mode OFF, seed CCD files, then click Scan CCD.

## 5. Final Flow Summary

On the Demo Simulator page in Demo Mode OFF, add a concise expected final result note:

Expected final seeded flow: 14 payments with beneficiary bank, 1 rejected by scheme, 1 rejected by beneficiary bank. No payment-level clearing is claimed from settlement summary.


## Documentation Updates

Update root README.md with a concise demo runbook section:

End-to-End Demo Runbook

Include:

## Demo Mode ON
Use for scripted presentation.
No backend files required.
Shows SME-aligned mocked flow.

## Demo Mode OFF

Include exact sequence:

cd C:\git_repos\payment_tracking_agent

.\scripts\seed-local-demo-files.ps1 -Phase clean
.\scripts\seed-local-demo-files.ps1 -Phase ccd
## Click Scan CCD

.\scripts\seed-local-demo-files.ps1 -Phase settlement
## Click Check settlement

.\scripts\seed-local-demo-files.ps1 -Phase returns
## Click Check returns

Explain expected final ledger counts:

14 WITH BENEFICIARY BANK
1 REJECTED BY SCHEME
1 REJECTED BY BENEFICIARY BANK
0 CLEARED

Add a note:

FedACH settlement summary is summary-level evidence only. The demo does not mark individual payments as cleared from settlement summary.

## Files Likely To Change

Frontend files may include:

frontend/src/pages/DemoSimulatorPage.tsx
frontend/src/components/LocalFolderDemoControls.tsx
frontend/src/components/LiveBatchDashboard.tsx
frontend/src/components/LiveCustomerDashboard.tsx
frontend/src/components/LivePaymentSearch.tsx
frontend/src/styles/app.css

Docs may include:

README.md

Only update other frontend/docs files if necessary.

## Do Not Do

Do not modify backend source files.
Do not modify backend tests.
Do not modify backend API behavior.
Do not implement new parsing.
Do not add LLM calls.
Do not add authentication.
Do not add dependencies.
Do not change Demo Mode ON data.
Do not commit.

## Validation

After implementation, these must pass:

cd frontend
npm run build

Backend tests are not required unless backend files are accidentally changed.

## Expected Summary

Summarize:

files changed
UX copy/runbook updates
README runbook updates
confirmation that no backend files changed
validation result