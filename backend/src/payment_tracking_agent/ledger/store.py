"""In-memory payment ledger store (Prompt 09).

Deliberately non-persistent. Reset clears the ledger so the demo can be
replayed from a clean state alongside the folder-watcher scenario store.
"""

from __future__ import annotations

import threading
from datetime import datetime

from payment_tracking_agent.models.ledger import (
    Payment,
    PaymentEvidence,
    PaymentStatus,
    PaymentStatusEvent,
)


class PaymentLedger:
    """Thread-safe in-memory ledger keyed by payment_id."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._payments: dict[str, Payment] = {}

    def reset(self) -> None:
        with self._lock:
            self._payments.clear()

    def add_payments(self, payments: list[Payment]) -> list[Payment]:
        """Insert payments. Existing payment_ids are left untouched."""
        added: list[Payment] = []
        with self._lock:
            for payment in payments:
                if payment.payment_id in self._payments:
                    continue
                self._payments[payment.payment_id] = payment
                added.append(payment)
        return added

    def list_payments(self) -> list[Payment]:
        with self._lock:
            return list(self._payments.values())

    def list_by_batch(self, batch_key: str) -> list[Payment]:
        with self._lock:
            return [p for p in self._payments.values() if p.batch_key == batch_key]

    def get_payment(self, payment_id: str) -> Payment | None:
        with self._lock:
            return self._payments.get(payment_id)

    def append_status(
        self,
        payment_id: str,
        status: PaymentStatus,
        evidence: PaymentEvidence,
        at: datetime,
    ) -> Payment | None:
        """Record a new status event on a payment.

        No-op if the payment is already at the target status or does not exist.
        """
        with self._lock:
            payment = self._payments.get(payment_id)
            if payment is None or payment.current_status == status:
                return payment
            payment.current_status = status
            payment.status_history.append(
                PaymentStatusEvent(status=status, at=at, evidence=evidence)
            )
            payment.evidence.append(evidence)
            return payment


_ledger = PaymentLedger()


def get_payment_ledger() -> PaymentLedger:
    """FastAPI dependency-friendly accessor for the singleton ledger."""
    return _ledger
