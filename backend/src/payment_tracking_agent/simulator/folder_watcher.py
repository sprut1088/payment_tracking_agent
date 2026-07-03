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
from payment_tracking_agent.models.demo_flow import (
    BatchIntake,
    BatchIntakeStatus,
    DemoFlowConfigView,
    DetectedFile,
    FileKind,
    ScanResult,
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
    ) -> None:
        self._settings = settings or default_settings
        self._store = store or get_scenario_state()

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
            result.new_files.append(file)
            result.new_batches.append(batch.batch_id)

        self._advance_all(now, result)
        return result

    def check_settlement(self, now: datetime | None = None) -> ScanResult:
        """Discover new settlement and scheme-reject files."""
        now = now or datetime.now(timezone.utc)
        self.ensure_directories()
        cfg = self.config_view
        result = ScanResult(scanned_at=now)

        for directory, kind in (
            (cfg.settlement_dir, FileKind.SETTLEMENT),
            (cfg.scheme_reject_dir, FileKind.SCHEME_REJECT),
        ):
            for file in self._list_new_files(directory, kind, now):
                if not self._attach_to_batch(file):
                    self._store.record_detected(file)
                result.new_files.append(file)

        self._advance_all(now, result)
        return result

    def check_returns(self, now: datetime | None = None) -> ScanResult:
        """Discover new NACHA return files."""
        now = now or datetime.now(timezone.utc)
        self.ensure_directories()
        cfg = self.config_view
        result = ScanResult(scanned_at=now)

        for file in self._list_new_files(cfg.returns_dir, FileKind.RETURN, now):
            if not self._attach_to_batch(file):
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
            if batch.status == BatchIntakeStatus.COMPLETE:
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

    def _attach_to_batch(self, file: DetectedFile) -> bool:
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
                return True
        return False


_watcher = FolderWatcher()


def get_folder_watcher() -> FolderWatcher:
    """FastAPI dependency-friendly accessor for the singleton watcher."""
    return _watcher
