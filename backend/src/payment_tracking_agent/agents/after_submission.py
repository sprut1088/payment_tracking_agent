"""AfterPaymentSubmissionAgent stub.

Responsibilities (implemented in a later prompt):
- Consume processing-engine / PEP+ evidence and mark payments ``WITH SCHEME``.
- Read settlement evidence and mark cleared payments ``CLEARED``.
- Mark submitted-but-unsettled payments ``WITH BENEFICIARY BANK``.
- Identify reconciliation exceptions.
"""

from __future__ import annotations


class AfterPaymentSubmissionAgent:
    """Placeholder. Implementation deferred to a later prompt."""

    def run(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("AfterPaymentSubmissionAgent is not implemented yet.")
