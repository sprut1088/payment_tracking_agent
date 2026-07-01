# Agents

Placeholder. Full I/O contracts and prompts are added in later build steps.

## BeforePaymentSubmissionAgent

- Parses CCD, runs syntax validation, creates payment records at `WITH BANK`.
- Runs historical similarity analysis, flags risky payments.
- Returns validation status, syntax findings, historical-risk findings,
  payment records created, and recommended user action.

## AfterPaymentSubmissionAgent

- Consumes processing-engine / PEP+ evidence, advances to `WITH SCHEME`.
- Reads settlement evidence, advances cleared to `CLEARED`, holds the rest at
  `WITH BENEFICIARY BANK`.
- Returns scheme submission status, settlement summary, cleared/pending
  counts, reconciliation findings, and status updates applied.

## ReturnFileAgent

- Parses NACHA return files, extracts reason codes and original trace numbers.
- Matches returns to prior payments and transitions them to `REJECTED`.
- Returns records parsed, matches, unmatched returns, customer-friendly
  message, and recommended action.

## PaymentLifecycleOrchestrator

- Runs the lifecycle across configured demo cycles.
- Maintains the payment status ledger and coordinates the other agents.
- Emits event log and agent trace.

## AIExplanationAgent

- Explains deterministic evidence and generates customer-safe messages.
- Never invents payment status. Cites evidence limitations when applicable.
