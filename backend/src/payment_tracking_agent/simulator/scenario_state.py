"""In-memory scenario state store for the local-folder demo flow.

Holds the set of batches discovered from CCD file drops and the files the
scanner has already seen. Thread-safe for the low concurrency of a demo UI.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from payment_tracking_agent.models.demo_flow import (
    BatchIntake,
    BatchIntakeStatus,
    DetectedFile,
    SettlementSchemeEvidenceStatus,
)


class ScenarioStateStore:
    """In-memory store of demo-flow scenario state."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._batches: dict[str, BatchIntake] = {}
        self._detected_files: dict[Path, DetectedFile] = {}

    def reset(self) -> None:
        with self._lock:
            self._batches.clear()
            self._detected_files.clear()

    def has_seen(self, path: Path) -> bool:
        with self._lock:
            return path in self._detected_files

    def record_detected(self, file: DetectedFile) -> None:
        with self._lock:
            self._detected_files.setdefault(file.path, file)

    def list_detected_files(self) -> list[DetectedFile]:
        with self._lock:
            return list(self._detected_files.values())

    def register_batch(self, batch: BatchIntake) -> None:
        with self._lock:
            self._batches[batch.batch_id] = batch
            self._detected_files.setdefault(batch.ccd_file.path, batch.ccd_file)

    def get_batch(self, batch_id: str) -> BatchIntake | None:
        with self._lock:
            return self._batches.get(batch_id)

    def list_batches(self) -> list[BatchIntake]:
        with self._lock:
            return list(self._batches.values())

    def attach_file(self, batch_id: str, file: DetectedFile) -> bool:
        """Attach a detected file to a batch. Returns True if attached."""
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return False
            bucket = {
                "settlement": batch.settlement_files,
                "scheme_reject": batch.scheme_reject_files,
                "return": batch.return_files,
            }.get(file.kind.value)
            if bucket is None:
                return False
            if any(existing.path == file.path for existing in bucket):
                return False
            bucket.append(file)
            self._detected_files.setdefault(file.path, file)
            self._refresh_settlement_scheme_status(batch)
            return True

    @staticmethod
    def _refresh_settlement_scheme_status(batch: BatchIntake) -> None:
        has_settlement = bool(batch.settlement_files)
        has_scheme_reject = bool(batch.scheme_reject_files)
        if has_settlement and has_scheme_reject:
            batch.settlement_scheme_status = (
                SettlementSchemeEvidenceStatus.SETTLEMENT_AND_SCHEME_REJECT_AVAILABLE
            )
        elif has_settlement:
            batch.settlement_scheme_status = (
                SettlementSchemeEvidenceStatus.SETTLEMENT_AVAILABLE
            )
        elif has_scheme_reject:
            batch.settlement_scheme_status = (
                SettlementSchemeEvidenceStatus.SCHEME_REJECT_AVAILABLE
            )
        else:
            batch.settlement_scheme_status = SettlementSchemeEvidenceStatus.NONE_AVAILABLE

    def advance_status(self, batch_id: str, now: datetime) -> bool:
        """Advance batch status based on elapsed time. Returns True if changed."""
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return False
            new_status = batch.status
            if (
                batch.status == BatchIntakeStatus.AWAITING_SETTLEMENT
                and now >= batch.expected_settlement_scan_at
            ):
                new_status = BatchIntakeStatus.AWAITING_RETURNS
            if (
                new_status == BatchIntakeStatus.AWAITING_RETURNS
                and now >= batch.expected_returns_scan_at
            ):
                new_status = BatchIntakeStatus.COMPLETE
            if new_status != batch.status:
                batch.status = new_status
                return True
            return False


_store = ScenarioStateStore()


def get_scenario_state() -> ScenarioStateStore:
    """FastAPI dependency-friendly accessor for the singleton store."""
    return _store
