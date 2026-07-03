# Demo Scenarios

The simulator runs configurable batch cycles. Real-world cycles may be 10:00, 14:00, and 18:00 GMT. The demo also supports accelerated schedules such as 10:00, 10:02, 10:04, and 10:06, as well as manual run-next-cycle mode.

---

## SME-Confirmed Demo Principle

Settlement summary does not identify individual customer payments as cleared.

Therefore, settlement summary should move payments to:

`WITH BENEFICIARY BANK`

Return files later identify rejected payments by original trace number.

---

## Scenario 10:00 — Batch submitted and settlement summary received

- Bank user uploads a CCD file.
- The CCD file contains individual payment traces.
- Bank-side syntax validation passes.
- Payments move to `SENT TO SCHEME`.
- Scheme validation passes.
- Settlement summary is received.
- Because settlement is summary-level, payments move to `WITH BENEFICIARY BANK`.
- No individual payment is marked as cleared from the summary file alone.

Example result:

| Trace | Stage |
|---|---|
| T001 | WITH BENEFICIARY BANK |
| T002 | WITH BENEFICIARY BANK |
| T003 | WITH BENEFICIARY BANK |
| T004 | WITH BENEFICIARY BANK |

---

## Scenario 10:02 — Return file arrives for prior cycle

- A new CCD file is uploaded for the 10:02 cycle.
- Bank-side validation passes for the new file.
- A NACHA return file also arrives for one or more payments from the 10:00 cycle.
- The return file contains original trace number and return reason code.
- The system matches the return original trace number to the prior CCD entry trace number.
- Matched payments move to `REJECTED BY BENEFICIARY BANK`.

Example result:

| Trace | Previous Stage | New Stage | Reason |
|---|---|---|---|
| T004 | WITH BENEFICIARY BANK | REJECTED BY BENEFICIARY BANK | R01 - Insufficient Funds |

---

## Scenario 10:04 and later — Cycle continues

- Additional CCD batches may be uploaded.
- Settlement summaries move submitted payments to `WITH BENEFICIARY BANK`.
- Return files may arrive for any earlier batch.
- The system keeps updating the payment ledger by trace number.
- Dashboards reflect status across batches, customers, dates, and payments.

---

## Four-Payment Example

Assume a CCD file contains four payments of 100 USD each.

| Trace | Customer | Amount |
|---|---|---:|
| T001 | Customer A | 100 |
| T002 | Customer B | 100 |
| T003 | Customer C | 100 |
| T004 | Customer D | 100 |

### Upload and bank validation pass

All four move to:

`SENT TO SCHEME`

### Settlement summary received

All four move to:

`WITH BENEFICIARY BANK`

No individual payment is marked as cleared.

### Later return file received

Return file contains:

| Original Trace | Return Reason |
|---|---|
| T004 | R01 - Insufficient Funds |

Final visible statuses:

| Trace | Stage |
|---|---|
| T001 | WITH BENEFICIARY BANK |
| T002 | WITH BENEFICIARY BANK |
| T003 | WITH BENEFICIARY BANK |
| T004 | REJECTED BY BENEFICIARY BANK |

---

## Future Demo Enhancements

If a future item-level clearing artifact is provided, the simulator may support a final cleared/completed stage. Until then, summary settlement alone should not mark individual payments as cleared.
