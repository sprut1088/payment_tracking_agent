# Documentation

Design notes for the ACH Payment Tracking Agent.

Start here:

- [01-business-understanding.md](01-business-understanding.md) — SME-confirmed ACH payment flow, status stages, settlement interpretation, return matching, and AI role

Supporting documents:

- [architecture.md](architecture.md) — System overview, component map, data flow, and ledger responsibility
- [agents.md](agents.md) — Agent responsibilities and evidence-backed stage transitions
- [statuses.md](statuses.md) — Business stages, secondary statuses, and truth rules
- [demo-scenarios.md](demo-scenarios.md) — Demo storylines and configurable cycle behavior

## Important SME-confirmed rule

FedACH settlement evidence used in this PoC is summary-level. It moves submitted payments to `WITH BENEFICIARY BANK`; it does not prove individual customer payments are cleared.

Only NACHA return evidence, matched by original trace number, moves a payment to `REJECTED BY BENEFICIARY BANK`.
