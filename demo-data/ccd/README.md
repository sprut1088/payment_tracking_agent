# CCD Upload Files

Fixed-width ACH CCD files consumed by the BeforePaymentSubmissionAgent.

Each file follows the standard NACHA record structure:

- `1` File Header
- `5` Batch Header
- `6` Entry Detail (one per tracked payment)
- `8` Batch Control
- `9` File Control

Real fixture files are added in a later prompt.
