"""Local-folder watcher for the demo flow.

Scans the configured demo-flow directory tree for CCD, settlement,
scheme-reject, and NACHA return files. Registers newly seen files with the
scenario state store and advances batch status based on elapsed time.

This module does not parse ACH file contents. Correlation between files and
batches is intentionally simple for this foundation prompt:

- Any new file in the inbox folder starts a new batch. The file's stem is used
  as the batch id.
- Any new file in a related folder (settlement / scheme-reject / returns) is
  attached to a batch whose id is a prefix of the file's stem. If no batch
  matches, the file is recorded as seen but left unattached.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from payment_tracking_agent.config import Settings, settings as default_settings
from payment_tracking_agent.ledger.store import PaymentLedger, get_payment_ledger
from payment_tracking_agent.models.demo_flow import (
    BatchIntake,
    BatchIntakeStatus,
    DemoFlowConfigView,
    DetectedFile,
    FileKind,
    ScanResult,
)
from payment_tracking_agent.models.ledger import (
    Payment,
    PaymentEvidence,
    PaymentStatus,
    PaymentStatusEvent,
)
from payment_tracking_agent.parsers.ccd import (
    ParsedCcdEntry,
    ParsedCcdFile,
    mask_account_number,
    parse_ccd_file,
)
from payment_tracking_agent.parsers.scheme_reject import (
    SchemeRejectRecord,
    parse_scheme_reject_file,
)
from payment_tracking_agent.simulator.scenario_state import (
    ScenarioStateStore,
    get_scenario_state,
)


class FolderWatcher:
    """Filesystem scanner for the local-folder demo flow."""

    def __init__(
        self,
        settings: Settings | None = None,
        store: ScenarioStateStore | None = None,
        ledger: PaymentLedger | None = None,
    ) -> None:
        self._settings = settings or default_settings
        self._store = store or get_scenario_state()
        self._ledger = ledger or get_payment_ledger()

    @property
    def config_view(self) -> DemoFlowConfigView:
        s = self._settings
        root = Path(s.demo_flow_root)
        return DemoFlowConfigView(
            demo_flow_root=root,
            inbox_dir=root / s.inbox_subdir,
            settlement_dir=root / s.settlement_subdir,
            scheme_reject_dir=root / s.scheme_reject_subdir,
            returns_dir=root / s.returns_subdir,
            processed_dir=root / s.processed_subdir,
            settlement_delay_seconds=s.settlement_delay_seconds,
            returns_delay_seconds=s.returns_delay_seconds,
            poll_interval_seconds=s.poll_interval_seconds,
        )

    def ensure_directories(self) -> None:
        cfg = self.config_view
        for directory in (
            cfg.inbox_dir,
            cfg.settlement_dir,
            cfg.scheme_reject_dir,
            cfg.returns_dir,
            cfg.processed_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def scan_ccd(self, now: datetime | None = None) -> ScanResult:
        """Discover new CCD files in the inbox and register batches."""
        now = now or datetime.now(timezone.utc)
        self.ensure_directories()
        cfg = self.config_view
        result = ScanResult(scanned_at=now)

        for file in self._list_new_files(cfg.inbox_dir, FileKind.CCD, now):
            batch = self._new_batch_from_ccd(file, now)
            self._store.register_batch(batch)
            self._create_payments_from_ccd(batch.batch_id, file, now)
            result.new_files.append(file)
            result.new_batches.append(batch.batch_id)

        self._advance_all(now, result)
        return result

    def check_settlement(self, now: datetime | None = None) -> ScanResult:
        """Discover new settlement and scheme-reject files and update the ledger.

        Scheme rejects are applied before settlement so that a payment matched
        by trace stays in ``REJECTED BY SCHEME`` rather than being moved to
        ``WITH BENEFICIARY BANK``. Settlement is treated as summary evidence
        only; no payment-level clearing is claimed.
        """
        now = now or datetime.now(timezone.utc)
        self.ensure_directories()
        cfg = self.config_view
        result = ScanResult(scanned_at=now)

        reject_pending: list[tuple[str, DetectedFile]] = []
        settlement_pending: list[tuple[str, DetectedFile]] = []

        for file in self._list_new_files(cfg.scheme_reject_dir, FileKind.SCHEME_REJECT, now):
            batch_key = self._attach_to_batch(file)
            if batch_key is None:
                self._store.record_detected(file)
            else:
                reject_pending.append((batch_key, file))
            result.new_files.append(file)

        for file in self._list_new_files(cfg.settlement_dir, FileKind.SETTLEMENT, now):
            batch_key = self._attach_to_batch(file)
            if batch_key is None:
                self._store.record_detected(file)
            else:
                settlement_pending.append((batch_key, file))
            result.new_files.append(file)

        for batch_key, file in reject_pending:
            self._apply_scheme_reject(batch_key, file, now)

        for batch_key, file in settlement_pending:
            self._apply_settlement_summary(batch_key, file, now)

        self._advance_all(now, result)
        return result

    def check_returns(self, now: datetime | None = None) -> ScanResult:
        """Discover new NACHA return files."""
        now = now or datetime.now(timezone.utc)
        self.ensure_directories()
        cfg = self.config_view
        result = ScanResult(scanned_at=now)

        for file in self._list_new_files(cfg.returns_dir, FileKind.RETURN, now):
            if self._attach_to_batch(file) is None:
                self._store.record_detected(file)
            result.new_files.append(file)

        self._advance_all(now, result)
        return result

    def scan_once(self, now: datetime | None = None) -> ScanResult:
        """Run all three scan phases in one pass (convenience only)."""
        now = now or datetime.now(timezone.utc)
        ccd = self.scan_ccd(now)
        settlement = self.check_settlement(now)
        returns = self.check_returns(now)
        return ScanResult(
            scanned_at=now,
            new_files=[*ccd.new_files, *settlement.new_files, *returns.new_files],
            new_batches=[*ccd.new_batches, *settlement.new_batches, *returns.new_batches],
            batches_advanced=list(
                dict.fromkeys(
                    [*ccd.batches_advanced, *settlement.batches_advanced, *returns.batches_advanced]
                )
            ),
        )

    def _advance_all(self, now: datetime, result: ScanResult) -> None:
        for batch in self._store.list_batches():
            if batch.status == BatchIntakeStatus.RETURN_EVIDENCE_RECEIVED:
                continue
            if self._store.advance_status(batch.batch_id, now):
                if batch.batch_id not in result.batches_advanced:
                    result.batches_advanced.append(batch.batch_id)

    def _list_new_files(
        self, directory: Path, kind: FileKind, now: datetime
    ) -> list[DetectedFile]:
        if not directory.exists():
            return []
        detected: list[DetectedFile] = []
        for entry in sorted(directory.iterdir()):
            if not entry.is_file():
                continue
            if self._store.has_seen(entry):
                continue
            stat = entry.stat()
            detected.append(
                DetectedFile(
                    path=entry,
                    filename=entry.name,
                    kind=kind,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    discovered_at=now,
                )
            )
        return detected

    def _new_batch_from_ccd(self, file: DetectedFile, now: datetime) -> BatchIntake:
        batch_id = file.path.stem
        return BatchIntake(
            batch_id=batch_id,
            ccd_file=file,
            uploaded_at=now,
            expected_settlement_scan_at=now
            + timedelta(seconds=self._settings.settlement_delay_seconds),
            expected_returns_scan_at=now
            + timedelta(seconds=self._settings.returns_delay_seconds),
            status=BatchIntakeStatus.AWAITING_SETTLEMENT,
        )

    def _create_payments_from_ccd(
        self, batch_key: str, file: DetectedFile, now: datetime
    ) -> list[Payment]:
        parsed: ParsedCcdFile = parse_ccd_file(file.path)
        if not parsed.entries:
            return []

        status = (
            PaymentStatus.SENT_TO_SCHEME
            if parsed.syntax_valid
            else PaymentStatus.WITH_BANK
        )
        summary = (
            "CCD file uploaded and bank-side syntax validation passed."
            if parsed.syntax_valid
            else "CCD file uploaded but bank-side syntax validation failed; payment held with bank."
        )
        source = "CCD upload scan"

        payments: list[Payment] = []
        for index, entry in enumerate(parsed.entries, start=1):
            payments.append(self._build_payment(batch_key, file, entry, index, status, source, summary, now))
        return self._ledger.add_payments(payments)

    @staticmethod
    def _build_payment(
        batch_key: str,
        file: DetectedFile,
        entry: ParsedCcdEntry,
        sequence: int,
        status: PaymentStatus,
        evidence_source: str,
        evidence_summary: str,
        now: datetime,
    ) -> Payment:
        evidence = PaymentEvidence(
            source=evidence_source, summary=evidence_summary, recorded_at=now
        )
        payment_id = f"{batch_key}:{sequence:04d}"
        return Payment(
            payment_id=payment_id,
            batch_key=batch_key,
            source_file=file.filename,
            trace_number=entry.trace_number,
            transaction_code=entry.transaction_code,
            receiving_dfi_identification=entry.receiving_dfi_identification,
            masked_account_number=mask_account_number(entry.dfi_account_number),
            amount_cents=entry.amount_cents,
            individual_id_number=entry.individual_id_number,
            individual_name=entry.individual_name,
            current_status=status,
            status_history=[
                PaymentStatusEvent(status=status, at=now, evidence=evidence),
            ],
            evidence=[evidence],
        )

    def _attach_to_batch(self, file: DetectedFile) -> str | None:
        """Attach a file to the best-matching batch and return its batch id."""
        stem = file.path.stem
        # Longest matching batch id wins so BATCH_001_RETURN prefers BATCH_001
        # over a shorter BATCH.
        candidates = sorted(
            (b for b in self._store.list_batches() if stem.startswith(b.batch_id)),
            key=lambda b: len(b.batch_id),
            reverse=True,
        )
        for batch in candidates:
            if self._store.attach_file(batch.batch_id, file):
                return batch.batch_id
        return None

    def _apply_scheme_reject(
        self, batch_key: str, file: DetectedFile, now: datetime
    ) -> None:
        parsed = parse_scheme_reject_file(file.path)
        for record in parsed.records:
            for payment in self._ledger.list_by_batch(batch_key):
                if not payment.trace_number:
                    continue
                if payment.trace_number != record.trace_number:
                    continue
                if payment.current_status == PaymentStatus.REJECTED_BY_SCHEME:
                    continue
                evidence = PaymentEvidence(
                    source=f"Scheme reject file {file.filename}",
                    summary=self._scheme_reject_summary(record),
                    recorded_at=now,
                )
                self._ledger.append_status(
                    payment.payment_id,
                    PaymentStatus.REJECTED_BY_SCHEME,
                    evidence,
                    at=now,
                )

    def _apply_settlement_summary(
        self, batch_key: str, file: DetectedFile, now: datetime
    ) -> None:
        summary = (
            "Settlement summary evidence received for this batch; "
            "payment moved to beneficiary bank. "
            "Settlement summary is not payment-level clearing evidence."
        )
        for payment in self._ledger.list_by_batch(batch_key):
            if payment.current_status != PaymentStatus.SENT_TO_SCHEME:
                continue
            evidence = PaymentEvidence(
                source=f"Settlement summary file {file.filename}",
                summary=summary,
                recorded_at=now,
            )
            self._ledger.append_status(
                payment.payment_id,
                PaymentStatus.WITH_BENEFICIARY_BANK,
                evidence,
                at=now,
            )

    @staticmethod
    def _scheme_reject_summary(record: SchemeRejectRecord) -> str:
        parts = [
            f"Scheme reject file matched this payment's trace number ({record.trace_number})."
        ]
        if record.reason_code and record.reason:
            parts.append(f"Scheme reason code {record.reason_code}: {record.reason}")
        elif record.reason_code:
            parts.append(f"Scheme reason code {record.reason_code}.")
        elif record.reason:
            parts.append(f"Scheme reason: {record.reason}")
        return " ".join(parts)


_watcher = FolderWatcher()


def get_folder_watcher() -> FolderWatcher:
    """FastAPI dependency-friendly accessor for the singleton watcher."""
    return _watcher
