"""In-memory payment ledger store (Prompt 09).

Deliberately non-persistent. Reset clears the ledger so the demo can be
replayed from a clean state alongside the folder-watcher scenario store.
"""

from __future__ import annotations

import threading

from payment_tracking_agent.models.ledger import Payment


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

    def get_payment(self, payment_id: str) -> Payment | None:
        with self._lock:
            return self._payments.get(payment_id)


_ledger = PaymentLedger()


def get_payment_ledger() -> PaymentLedger:
    """FastAPI dependency-friendly accessor for the singleton ledger."""
    return _ledger
