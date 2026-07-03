# Prompt 08 — Refine Local Folder Evidence State

Read `.github/copilot-instructions.md` before editing.

## Objective

Refine the Local Folder Demo Flow so the backend state and frontend labels clearly describe file-evidence monitoring.

This step should not implement ACH parsing or a payment ledger.

The current file detection works, but the local-folder panel has confusing wording:

- After settlement/scheme-reject evidence is detected, the batch can still show `AWAITING_SETTLEMENT`.
- The summary card `Complete` is misleading because ACH returns can arrive later or repeatedly.
- The local-folder panel should make clear that it shows file-evidence state, not final customer payment outcome.

## Required Backend Behavior

Update backend local-folder demo state logic so:

1. After `scan-ccd`, a detected CCD batch is in:

```text
AWAITING_SETTLEMENT