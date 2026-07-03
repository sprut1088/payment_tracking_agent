# Prompt 06 — Add Demo Mode Toggle and SME-Aligned UI Data

Read `.github/copilot-instructions.md` before editing.

Frontend only. Do not modify backend files.

## Objective

Add a top-right `Demo Mode` toggle to the application.

When Demo Mode is ON:
- The UI shows predefined mocked SME-aligned demo data.
- The UI does not require backend files.
- This mode is used for scripted presentations.

When Demo Mode is OFF:
- The UI uses the real backend local-folder demo flow controls.
- The user can ensure folders, scan CCD uploads, check settlement/scheme reject files, and check return files.

## Important SME Status Logic

Use these UI statuses:

- `WITH BANK`
- `SENT TO SCHEME`
- `WITH BENEFICIARY BANK`
- `REJECTED BY SCHEME`
- `REJECTED BY BENEFICIARY BANK`

Do not show `CLEARED` in mock dashboard data.

Settlement summary is summary-level evidence only. It does not prove individual payment clearing.

## Required Demo Mode Mock Story

Update mocked data to show this flow:

### 11:00 Cycle

- CCD batch file uploaded.
- 4 payments of $100 each.
- Total CCD amount = $400.
- Bank-side syntax validation passes.
- Payments move to `SENT TO SCHEME`.
- Settlement summary arrives for $300.
- Scheme reject file arrives for $100.

Result:
- 3 payments move to `WITH BENEFICIARY BANK`
- 1 payment moves to `REJECTED BY SCHEME`

### 11:04 Cycle

- NACHA return file arrives for 1 payment that was previously with beneficiary bank.
- That payment moves to `REJECTED BY BENEFICIARY BANK`.
- Remaining payments stay `WITH BENEFICIARY BANK`.

## Required UI Behavior

Add a `Demo Mode` toggle in the top-right header.

Default should be:

```text
Demo Mode ON
```

When toggled OFF, the UI should use real backend local-folder demo flow controls.

When toggled ON, the UI should show the SME-aligned mock data and story above.