"""ReturnFileAgent stub.

Responsibilities (implemented in a later prompt):
- Parse NACHA return file.
- Extract return reason code and original trace number.
- Link return records back to prior payments and mark ``REJECTED``.
- Produce customer-safe root cause and corrective guidance.
"""

from __future__ import annotations


class ReturnFileAgent:
    """Placeholder. Implementation deferred to a later prompt."""

    def run(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("ReturnFileAgent is not implemented yet.")
