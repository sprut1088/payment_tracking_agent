# Demo Scenarios

The simulator runs configurable batch cycles. Real-world cycles are 10:00,
14:00, and 18:00 GMT. The demo also supports accelerated schedules — for
example 10:00, 10:02, 10:04, 10:06 — as well as manual and
run-next-cycle modes.

## Scenario 10:00 — Held at beneficiary bank

- 20-payment CCD file uploaded.
- Syntax validation passes; historical analysis flags risky payments.
- Processing-engine validates and submits to scheme.
- Settlement evidence confirms 18 cleared.
- 2 payments are neither cleared nor returned → `WITH BENEFICIARY BANK`.

## Scenario 10:02 — Return file resolves prior held payments

- 15-payment CCD file uploaded.
- Settlement evidence confirms 12 cleared.
- NACHA return file arrives for the 2 payments held from the 10:00 cycle.
- Those 2 payments transition `WITH BENEFICIARY BANK` → `REJECTED`.

## Later cycles

- Additional batches may be processed.
- Returns may continue to arrive for earlier batches.
- Dashboards reflect status across batches, customers, and dates.

Scenario manifests live under
[../demo-data/scenarios](../demo-data/scenarios). Fixtures and full simulator
behavior are added in later prompts.
