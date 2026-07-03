# Prompt 04 — Backend Local Folder Demo Flow Foundation

Read `.github/copilot-instructions.md` before editing.

Backend only. Do not modify frontend files.

## Objective

Add the backend foundation for a local-folder-based ACH demo flow.

The demo requirement is:

- A user uploads or places a CCD batch file in a configured local Windows folder.
- The program treats that as batch upload time.
- Around +2 minutes, the program should look for related settlement and scheme reject files.
- Around +4 minutes, the program should look for related NACHA return files.
- Later steps will parse the files and update payment statuses.

This prompt should only implement configuration, folder scanning, scenario state, and API stubs. Do not implement ACH parsing yet.

## Use Existing Backend Package

Use the existing backend package already in this repo.

The import path is:

```text
payment_tracking_agent