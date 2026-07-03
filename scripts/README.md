# Scripts

Developer helper scripts for local runs.

- `dev-backend.ps1` — create/activate the backend venv, install deps, run
  FastAPI with reload.
- `dev-frontend.ps1` — install frontend deps and start the Vite dev server.
- `seed-local-demo-files.ps1` — copy predefined sample files into
  `backend/demo-inbox` by phase (`ccd`, `settlement`, `returns`, `all`,
  `clean`, `reset`) for Demo Mode OFF local-folder flow.
  Source fixtures default to `demo-data/local-folder-demo/batch_1100`.
  Prefer `-Phase clean`; `-Phase reset` is a compatibility alias.

Both scripts are safe to re-run.
