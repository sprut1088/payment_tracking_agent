# FedACH Settlement Reports

Sample settlement reports consumed by the AfterPaymentSubmissionAgent.

Segments used:

- `10` Header
- `20` Summary data
- `30` Grand trailer / net adjustment

Because settlement files are summary-level, payment-level clearing evidence
uses an accompanying synthetic detail file or explicit cleared-trace list.
Real fixtures are added in a later prompt.
