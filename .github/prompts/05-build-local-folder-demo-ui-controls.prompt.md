# Prompt 05 — Build Local Folder Demo UI Controls

Read `.github/copilot-instructions.md` before editing.

Frontend only. Do not modify backend files.

## Objective

Update the frontend demo UI so it can drive the backend local-folder demo flow that already exists.

The backend now exposes these endpoints:

```text
GET  /api/demo-flow/config
POST /api/demo-flow/ensure-folders
POST /api/demo-flow/scan-ccd
POST /api/demo-flow/check-settlement
POST /api/demo-flow/check-returns
GET  /api/demo-flow/state
POST /api/demo-flow/reset