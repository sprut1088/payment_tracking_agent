"""Demo customer historical rejection store (in-memory).

Loads customer-level rejection history from a JSON fixture. This is
**not** database persistence — it is a lightweight in-memory summary
source consumed by the AI risk classifier so it can classify customer
trend risk from deterministic history.

The default fixture ships at
``demo-data/local-folder-demo/customer-risk-history.json``.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE_PATH = (
    _REPO_ROOT / "demo-data" / "local-folder-demo" / "customer-risk-history.json"
)


@dataclass(frozen=True)
class CustomerRejection:
    occurred_at: datetime
    status: str
    reason_code: str
    reason_message: str


@dataclass(frozen=True)
class CustomerHistorySummary:
    """Rolled-up rejection history for one customer."""

    customer_id: str
    customer_name: str
    rejections_last_7d: int
    rejections_last_30d: int
    rejections_last_90d: int
    common_reason_codes: list[str]
    latest_rejection_at: datetime | None
    open_rejected_payments: int
    total_rejections: int

    def has_recent_activity(self) -> bool:
        return self.rejections_last_90d > 0

    def repeated_same_reason_in_7d(self) -> bool:
        return self.rejections_last_7d >= 2 and len(self.common_reason_codes) == 1


class CustomerHistoryStore:
    """In-memory store of demo customer rejection history."""

    def __init__(self, records: dict[str, list[CustomerRejection]] | None = None,
                 names: dict[str, str] | None = None) -> None:
        self._records: dict[str, list[CustomerRejection]] = records or {}
        self._names: dict[str, str] = names or {}

    @classmethod
    def from_fixture(cls, path: Path | None = None) -> CustomerHistoryStore:
        source = path or DEFAULT_FIXTURE_PATH
        if not source.exists():
            return cls()
        raw = json.loads(source.read_text(encoding="utf-8"))
        records: dict[str, list[CustomerRejection]] = {}
        names: dict[str, str] = {}
        for entry in raw.get("customers", []):
            customer_id = entry["customer_id"]
            names[customer_id] = entry.get("customer_name", customer_id)
            rejections: list[CustomerRejection] = []
            for rej in entry.get("rejections", []):
                occurred_at = datetime.fromisoformat(
                    rej["occurred_at"].replace("Z", "+00:00")
                )
                rejections.append(
                    CustomerRejection(
                        occurred_at=occurred_at,
                        status=rej.get("status", ""),
                        reason_code=rej.get("reason_code", ""),
                        reason_message=rej.get("reason_message", ""),
                    )
                )
            records[customer_id] = rejections
        return cls(records=records, names=names)

    def customer_name(self, customer_id: str, fallback: str = "") -> str:
        return self._names.get(customer_id, fallback or customer_id)

    def summary(
        self,
        customer_id: str,
        *,
        customer_name: str = "",
        now: datetime | None = None,
        open_rejected_payments: int = 0,
    ) -> CustomerHistorySummary:
        reference = now or datetime.now(timezone.utc)
        rejections = self._records.get(customer_id, [])
        cutoff_7d = reference - timedelta(days=7)
        cutoff_30d = reference - timedelta(days=30)
        cutoff_90d = reference - timedelta(days=90)

        recent_90d = [r for r in rejections if r.occurred_at >= cutoff_90d]
        recent_30d = [r for r in recent_90d if r.occurred_at >= cutoff_30d]
        recent_7d = [r for r in recent_30d if r.occurred_at >= cutoff_7d]
        latest = max((r.occurred_at for r in rejections), default=None)
        codes = Counter(r.reason_code for r in recent_90d if r.reason_code)
        # Most common codes ordered by frequency then code.
        common = [
            code for code, _count in sorted(
                codes.items(), key=lambda kv: (-kv[1], kv[0])
            )
        ]
        return CustomerHistorySummary(
            customer_id=customer_id,
            customer_name=self.customer_name(customer_id, customer_name),
            rejections_last_7d=len(recent_7d),
            rejections_last_30d=len(recent_30d),
            rejections_last_90d=len(recent_90d),
            common_reason_codes=common,
            latest_rejection_at=latest,
            open_rejected_payments=open_rejected_payments,
            total_rejections=len(rejections),
        )

    def customer_ids(self) -> Iterable[str]:
        return list(self._records.keys())


_default_store: CustomerHistoryStore | None = None


def get_customer_history_store() -> CustomerHistoryStore:
    global _default_store
    if _default_store is None:
        _default_store = CustomerHistoryStore.from_fixture()
    return _default_store


def set_customer_history_store(store: CustomerHistoryStore | None) -> None:
    """Testing helper. Replace or clear the singleton store."""
    global _default_store
    _default_store = store
