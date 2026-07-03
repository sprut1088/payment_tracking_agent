# Prompt 07 — Add Sample Local Demo Files and Seed Script

Read `.github/copilot-instructions.md` before editing.

This step adds sample files and helper scripts only.

Do not implement ACH parsing.
Do not implement payment ledger.
Do not modify frontend source code.
Do not modify backend API logic unless a small test helper is needed.

## Objective

Add predefined sample local files so Demo Mode OFF can demonstrate the backend local-folder flow.

The user should be able to seed files into the local demo folders in phases:

1. CCD upload file goes into `backend/demo-inbox/ccd`
2. Settlement and scheme reject files go into:
   - `backend/demo-inbox/settlement`
   - `backend/demo-inbox/scheme-reject`
3. NACHA return file goes into `backend/demo-inbox/returns`

The current backend should detect these files using the existing `/api/demo-flow/*` endpoints.

## Demo Story

Use one batch key:

```text
batch_1100