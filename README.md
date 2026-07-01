# ACH Payment Tracking Agent

End-to-end ACH payment flow tracking and intelligence platform. The system
answers the operational question:

> Where is this customer's ACH payment right now?

See [.github/copilot-instructions.md](.github/copilot-instructions.md) for the
full project mission, business rules, status truth rules, agent architecture,
and demo scenarios.

This repository is being built incrementally through the prompts in
[.github/prompts](.github/prompts). This bootstrap step (Prompt 01) only
creates the project skeleton — no ACH parsing, payment ledger, LLM logic, or
real PEP+ integration is implemented yet.

## Structure

```text
payment-tracking-agent/
  backend/            Python backend, agent workflow, APIs
  frontend/           React + TypeScript + Vite demo UI
  demo-data/          CCD, settlement, return, historical sample artifacts
  docs/               Architecture and design documentation
  scripts/            Local developer helper scripts
  .github/
    copilot-instructions.md
    prompts/          Ordered build prompts
```

## Core business statuses

- `WITH BANK`
- `WITH SCHEME`
- `WITH BENEFICIARY BANK`
- `CLEARED`
- `REJECTED`

Internal sub-statuses may be used but must roll up to the above. See the
copilot instructions for the full list and truth rules.

## Getting started

The backend and frontend are skeletons at this stage. Install commands are
listed in [backend/README.md](backend/README.md) and
[frontend/README.md](frontend/README.md). Convenience scripts live under
[scripts](scripts).
