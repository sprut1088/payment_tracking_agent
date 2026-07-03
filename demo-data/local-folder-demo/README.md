# Local Folder Demo Fixtures

Source fixtures for local-folder Demo Mode OFF flow.

Default seed source:

- `demo-data/local-folder-demo/batch_1100`

Expected fixture files:

- `ccd/batch_1100.ach`
- `settlement/batch_1100_settlement.dat`
- `scheme-reject/batch_1100_reject.json`
- `returns/batch_1100_return.ach`

These fixtures are copied into `backend/demo-inbox/*` by
`scripts/seed-local-demo-files.ps1`.
