# Prompt 04.1 — Refine Settlement and Scheme Reject Handling

Read `.github/copilot-instructions.md` before editing.

Backend only. Do not modify frontend files.

## Objective

Refine the local-folder demo flow foundation so a batch can have:

1. settlement file only
2. scheme reject file only
3. both settlement file and scheme reject file

This is required because a CCD batch may contain $1000 total, where $900 is represented in settlement summary and $100 is represented in scheme reject evidence.

Do not implement ACH/FedACH/NACHA parsing yet. This prompt is only about file-state modeling and API state.

## Required Behavior

When checking settlement/scheme-reject folders:

- If only settlement file exists, attach settlement file and status should reflect settlement evidence is available.
- If only scheme reject file exists, attach scheme reject file and status should reflect scheme reject evidence is available.
- If both settlement and scheme reject files exist for the same batch key, attach both files and status should reflect both are available.

Do not treat settlement and scheme reject as mutually exclusive.

## Required Status Update

If current enum/status model has only one value, add a combined status such as:

```text
SETTLEMENT_AND_SCHEME_REJECT_AVAILABLE