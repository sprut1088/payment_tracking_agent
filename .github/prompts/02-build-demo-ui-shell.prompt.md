# Prompt 02 — Build Demo UI Shell

Read `.github/copilot-instructions.md` before generating code.

## Objective

Build the first real frontend demo UI shell for the ACH Payment Tracking Agent.

Use existing `/frontend` React + TypeScript + Vite project.

Do not implement backend APIs, ACH parsing, payment ledger, LLM, or database logic in this step.

Use mocked frontend data only.

## Required UI Pages

Create these pages under `frontend/src/pages/`:

- `DemoSimulatorPage.tsx`
- `BatchDashboardPage.tsx`
- `CustomerDashboardPage.tsx`
- `PaymentSearchPage.tsx`

## Required Components

Create these components under `frontend/src/components/`:

- `AppShell.tsx`
- `ScenarioConfigPanel.tsx`
- `CycleTimeline.tsx`
- `PaymentStatusBoard.tsx`
- `BatchDashboard.tsx`
- `CustomerDashboard.tsx`
- `PaymentDetailDrawer.tsx`
- `AgentTracePanel.tsx`
- `EvidenceViewer.tsx`
- `StatusBadge.tsx`

## Required Types and Mock API

Create:

- `frontend/src/types/api.ts`
- `frontend/src/api/client.ts`

The mock API client should return demo data for:

- scenario list
- current simulation state
- batch dashboard
- customer dashboard
- payment detail

## UI Behavior

The default page should be Demo Simulator.

Use local React state for navigation.

Show these navigation items:

- Demo Simulator
- Batch Dashboard
- Customer Dashboard
- Payment Search

The Demo Simulator page should show an accelerated cycle example:

- 10:00 batch: 20 payments uploaded, 18 cleared, 2 with beneficiary bank
- 10:02 batch: 15 payments uploaded, 12 cleared, 2 returns arrive for prior batch

Use these statuses:

- WITH BANK
- WITH SCHEME
- WITH BENEFICIARY BANK
- CLEARED
- REJECTED

## Styling

Create or update:

- `frontend/src/styles/app.css`

Make the UI look like a polished enterprise demo using cards, tables, badges, and timeline sections.

No external UI library.

## Update App

Update:

- `frontend/src/App.tsx`
- `frontend/src/main.tsx`

so the new UI shell renders correctly.

## Validation

After implementation, these must pass:

```powershell
cd frontend
npm run build
npm run dev