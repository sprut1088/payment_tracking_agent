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
from payment_tracking_agent.models.ai_risk import (
    BatchRiskClassification,
    CustomerRiskClassification,
    RiskClassification,
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


    def set_risk_classification(
        self, payment_id: str, classification: RiskClassification
    ) -> Payment | None:
        """Stamp an AI risk classification onto a payment.

        The previous ``current_risk_classification`` (if any) is moved into
        ``risk_classification_history`` so callers can inspect the trend.
        Never mutates ``current_status``, ``status_history``, or ``evidence``.
        """
        with self._lock:
            payment = self._payments.get(payment_id)
            if payment is None:
                return None
            if payment.current_risk_classification is not None:
                payment.risk_classification_history.append(
                    payment.current_risk_classification
                )
            payment.current_risk_classification = classification
            return payment

    def set_customer_risk_classification(
        self, payment_id: str, classification: CustomerRiskClassification
    ) -> Payment | None:
        """Stamp customer-level risk classification onto a payment."""
        with self._lock:
            payment = self._payments.get(payment_id)
            if payment is None:
                return None
            if payment.current_customer_risk_classification is not None:
                payment.customer_risk_classification_history.append(
                    payment.current_customer_risk_classification
                )
            payment.current_customer_risk_classification = classification
            return payment

    def set_batch_risk_classification(
        self, payment_id: str, classification: BatchRiskClassification
    ) -> Payment | None:
        """Stamp batch-level risk classification onto a payment."""
        with self._lock:
            payment = self._payments.get(payment_id)
            if payment is None:
                return None
            if payment.current_batch_risk_classification is not None:
                payment.batch_risk_classification_history.append(
                    payment.current_batch_risk_classification
                )
            payment.current_batch_risk_classification = classification
            return payment


_ledger = PaymentLedger()


def get_payment_ledger() -> PaymentLedger:
    """FastAPI dependency-friendly accessor for the singleton ledger."""
    return _ledger
