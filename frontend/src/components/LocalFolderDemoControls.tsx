import { useCallback, useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  DemoFlowBatch,
  DemoFlowBatchStatus,
  DemoFlowConfig,
  DemoFlowScanResult,
  DemoFlowState,
  DropFileInfo,
  PaymentRecord,
  SettlementSchemeEvidenceStatus,
  UploadSummary,
} from "../types/api";

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function batchStatusLabel(status: DemoFlowBatchStatus): string {
  switch (status) {
    case "AWAITING_SETTLEMENT":
      return "Awaiting settlement / scheme evidence";
    case "AWAITING_RETURNS":
      return "Monitoring returns";
    case "RETURN_EVIDENCE_RECEIVED":
      return "Return evidence received";
    default:
      return status;
  }
}

function evidenceLabel(status: SettlementSchemeEvidenceStatus): string {
  switch (status) {
    case "NONE_AVAILABLE":
      return "None";
    case "SETTLEMENT_AVAILABLE":
      return "Settlement only";
    case "SCHEME_REJECT_AVAILABLE":
      return "Scheme reject only";
    case "SETTLEMENT_AND_SCHEME_REJECT_AVAILABLE":
      return "Settlement + scheme reject";
    default:
      return status;
  }
}

function sortBatchesNewestFirst(rows: DemoFlowBatch[]): DemoFlowBatch[] {
  return [...rows].sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at));
}

interface LocalFolderDemoControlsProps {
  config: DemoFlowConfig | null;
  flowState: DemoFlowState | null;
  liveUploads: UploadSummary[];
  livePayments: PaymentRecord[];
  dropFiles: DropFileInfo[];
  awaitingReviewCount: number;
  /** Called after any mutating action so the parent can re-fetch all data at once. */
  onRefresh: () => void;
}

export function LocalFolderDemoControls({
  config,
  flowState,
  liveUploads,
  livePayments,
  dropFiles,
  awaitingReviewCount,
  onRefresh,
}: LocalFolderDemoControlsProps) {
  const [lastScan, setLastScan] = useState<DemoFlowScanResult | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const runAction = useCallback(
    async (okMessage: string, action: () => Promise<void>) => {
      setIsBusy(true);
      setError(null);
      try {
        await action();
        setMessage(`${okMessage} at ${new Date().toLocaleTimeString()}`);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Request failed.");
      } finally {
        setIsBusy(false);
      }
    },
    [],
  );

  const sortedBatches = useMemo(
    () => sortBatchesNewestFirst(flowState?.batches ?? []),
    [flowState?.batches],
  );

  const summary = useMemo(() => {
    // Prefer ledger data (covers both demo-inbox and drop/ folder uploads).
    // Fall back to demo-inbox DemoFlowBatch counts if ledger is empty.
    if (liveUploads.length > 0) {
      const awaitingSettlement = liveUploads.filter((u) =>
        livePayments.some(
          (p) => p.sourceFile === u.file_name &&
            (p.currentStatus === "SENT TO SCHEME" || p.currentStatus === "WITH BANK"),
        ),
      ).length;
      const awaitingReturns = liveUploads.filter((u) => {
        const ps = livePayments.filter((p) => p.sourceFile === u.file_name);
        return ps.length > 0 && ps.some((p) => p.currentStatus === "WITH BENEFICIARY BANK");
      }).length;
      const returnEvidenceReceived = liveUploads.filter((u) =>
        livePayments.some(
          (p) => p.sourceFile === u.file_name && p.currentStatus === "REJECTED BY BENEFICIARY BANK",
        ),
      ).length;
      return {
        totalBatches: liveUploads.length,
        awaitingSettlement,
        awaitingReturns,
        returnEvidenceReceived,
        detectedFiles: liveUploads.length,
      };
    }
    const batches = flowState?.batches ?? [];
    return {
      totalBatches: batches.length,
      awaitingSettlement: batches.filter((b) => b.status === "AWAITING_SETTLEMENT").length,
      awaitingReturns: batches.filter((b) => b.status === "AWAITING_RETURNS").length,
      returnEvidenceReceived: batches.filter(
        (b) => b.status === "RETURN_EVIDENCE_RECEIVED",
      ).length,
      detectedFiles: flowState?.detected_files.length ?? 0,
    };
  }, [flowState, liveUploads, livePayments]);

  return (
    <section className="card">
      <header className="card__header">
        <h2 className="card__title">Local folder demo flow controls</h2>
        <p className="card__subtitle">
          Drive backend endpoints for folder setup and phased scanning: CCD,
          settlement/scheme reject, then returns. This panel shows file-evidence
          state only; it is not a final customer payment outcome and return
          files may still arrive later.
        </p>
      </header>

      <div className="action-row">
        <button
          type="button"
          className="button button--primary"
          disabled={isBusy}
          onClick={() =>
            void runAction("Folders ensured", async () => {
              await api.ensureDemoFlowFolders();
              onRefresh();
            })
          }
        >
          Ensure folders
        </button>
        <button
          type="button"
          className="button"
          disabled={isBusy}
          onClick={() =>
            void runAction("CCD scan complete", async () => {
              const scan = await api.scanDemoFlowCcd();
              setLastScan(scan);
              onRefresh();
            })
          }
        >
          Scan CCD
        </button>
        <button
          type="button"
          className="button"
          disabled={isBusy}
          onClick={() =>
            void runAction("Settlement check complete", async () => {
              const scan = await api.checkDemoFlowSettlement();
              setLastScan(scan);
              onRefresh();
            })
          }
        >
          Check settlement
        </button>
        <button
          type="button"
          className="button"
          disabled={isBusy}
          onClick={() =>
            void runAction("Returns check complete", async () => {
              const scan = await api.checkDemoFlowReturns();
              setLastScan(scan);
              onRefresh();
            })
          }
        >
          Check returns
        </button>
        <button
          type="button"
          className="button button--ghost"
          disabled={isBusy}
          onClick={() =>
            void runAction("State refreshed", async () => {
              onRefresh();
            })
          }
        >
          Refresh state
        </button>
        <button
          type="button"
          className="button button--ghost"
          disabled={isBusy}
          onClick={() =>
            void runAction("Demo-flow state reset", async () => {
              await api.resetDemoFlow();
              setLastScan(null);
              onRefresh();
            })
          }
        >
          Reset
        </button>
      </div>

      {message && <div className="local-flow__notice">{message}</div>}
      {awaitingReviewCount > 0 && (
        <div className="local-flow__notice local-flow__notice--review">
          {awaitingReviewCount} file{awaitingReviewCount !== 1 ? "s" : ""} awaiting review
          — open the <strong>Batch Dashboard</strong> to review corrections and accept or reject.
        </div>
      )}
      {error && <div className="local-flow__error">{error}</div>}

      <div className="local-flow__stats">
        <div className="local-flow__stat">
          <div className="local-flow__stat-label">Batches</div>
          <div className="local-flow__stat-value">{summary.totalBatches}</div>
        </div>
        <div className="local-flow__stat">
          <div className="local-flow__stat-label">Awaiting settlement</div>
          <div className="local-flow__stat-value">{summary.awaitingSettlement}</div>
        </div>
        <div className="local-flow__stat">
          <div className="local-flow__stat-label">Monitoring returns</div>
          <div className="local-flow__stat-value">{summary.awaitingReturns}</div>
        </div>
        <div className="local-flow__stat">
          <div className="local-flow__stat-label">Return evidence received</div>
          <div className="local-flow__stat-value">{summary.returnEvidenceReceived}</div>
        </div>
        <div className="local-flow__stat">
          <div className="local-flow__stat-label">Detected files</div>
          <div className="local-flow__stat-value">{summary.detectedFiles}</div>
        </div>
        <div className="local-flow__stat local-flow__stat--review">
          <div className="local-flow__stat-label">Awaiting review</div>
          <div className="local-flow__stat-value">{awaitingReviewCount}</div>
        </div>
      </div>

      {lastScan && (
        <div className="local-flow__scan-result">
          <span>Last scan: {formatTimestamp(lastScan.scanned_at)}</span>
          <span>New files: {lastScan.new_files.length}</span>
          <span>New batches: {lastScan.new_batches.length}</span>
          <span>Batches advanced: {lastScan.batches_advanced.length}</span>
        </div>
      )}

      {config && (
        <div className="local-flow__section">
          <h3 className="local-flow__section-title">Configured folders</h3>
          <div className="local-flow__paths">
            <div className="local-flow__path-item">
              <span className="local-flow__path-label">Root</span>
              <span className="local-flow__path-value">{config.demo_flow_root}</span>
            </div>
            <div className="local-flow__path-item">
              <span className="local-flow__path-label">CCD</span>
              <span className="local-flow__path-value">{config.inbox_dir}</span>
            </div>
            <div className="local-flow__path-item">
              <span className="local-flow__path-label">Settlement</span>
              <span className="local-flow__path-value">{config.settlement_dir}</span>
            </div>
            <div className="local-flow__path-item">
              <span className="local-flow__path-label">Scheme reject</span>
              <span className="local-flow__path-value">{config.scheme_reject_dir}</span>
            </div>
            <div className="local-flow__path-item">
              <span className="local-flow__path-label">Returns</span>
              <span className="local-flow__path-value">{config.returns_dir}</span>
            </div>
            <div className="local-flow__path-item">
              <span className="local-flow__path-label">Processed</span>
              <span className="local-flow__path-value">{config.processed_dir}</span>
            </div>
          </div>
        </div>
      )}

      <div className="local-flow__section">
        <h3 className="local-flow__section-title">Batch state</h3>
        {liveUploads.length > 0 ? (
          /* Ledger view — covers both demo-inbox and drop/ folder uploads */
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Lifecycle</th>
                  <th className="table__num">Entries</th>
                  <th className="table__num">Sent&nbsp;to&nbsp;scheme</th>
                  <th className="table__num">With&nbsp;beneficiary</th>
                  <th className="table__num">Rejected&nbsp;(scheme)</th>
                  <th className="table__num">Rejected&nbsp;(return)</th>
                  <th>Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {[...liveUploads]
                  .sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at))
                  .map((u) => {
                    const ps = livePayments.filter((p) => p.sourceFile === u.file_name);
                    const sentToScheme = ps.filter((p) => p.currentStatus === "SENT TO SCHEME").length;
                    const withBeneficiary = ps.filter((p) => p.currentStatus === "WITH BENEFICIARY BANK").length;
                    const rejectedScheme = ps.filter((p) => p.currentStatus === "REJECTED BY SCHEME").length;
                    const rejectedReturn = ps.filter((p) => p.currentStatus === "REJECTED BY BENEFICIARY BANK").length;
                    let lifecycle = "With bank";
                    if (rejectedReturn > 0) lifecycle = "Return evidence received";
                    else if (withBeneficiary > 0) lifecycle = "Monitoring returns";
                    else if (rejectedScheme > 0) lifecycle = "Scheme reject received";
                    else if (sentToScheme > 0) lifecycle = "Sent to scheme";
                    return (
                      <tr key={u.upload_id}>
                        <td className="table__mono">{u.file_name}</td>
                        <td>{lifecycle}</td>
                        <td className="table__num">{u.entry_count}</td>
                        <td className="table__num">{sentToScheme}</td>
                        <td className="table__num">{withBeneficiary}</td>
                        <td className="table__num">{rejectedScheme}</td>
                        <td className="table__num">{rejectedReturn}</td>
                        <td>{formatTimestamp(u.uploaded_at)}</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        ) : (
          /* Demo-inbox view — fallback when ledger has no data yet */
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Batch key</th>
                  <th>Lifecycle</th>
                  <th>Settlement / scheme reject</th>
                  <th className="table__num">Settlement files</th>
                  <th className="table__num">Scheme rejects</th>
                  <th className="table__num">Return files</th>
                  <th>Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {sortedBatches.length === 0 && (
                  <tr>
                    <td colSpan={7} className="table__empty">
                      No batches yet. Place a CCD file in the demo-inbox or drop/ccd/input
                      folder, then run Scan CCD or wait for the scheduler.
                    </td>
                  </tr>
                )}
                {sortedBatches.map((batch) => (
                  <tr key={batch.batch_id}>
                    <td className="table__mono">{batch.batch_id}</td>
                    <td>{batchStatusLabel(batch.status)}</td>
                    <td>{evidenceLabel(batch.settlement_scheme_status)}</td>
                    <td className="table__num">{batch.settlement_files.length}</td>
                    <td className="table__num">{batch.scheme_reject_files.length}</td>
                    <td className="table__num">{batch.return_files.length}</td>
                    <td>{formatTimestamp(batch.uploaded_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="local-flow__section">
        <h3 className="local-flow__section-title">Detected files</h3>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Location</th>
                <th className="table__num">Size / Entries</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {liveUploads.length === 0 &&
                dropFiles.length === 0 &&
                (flowState?.detected_files ?? []).length === 0 && (
                  <tr>
                    <td colSpan={4} className="table__empty">
                      No processed files yet. Drop files in drop/ccd/input, drop/settlement/input,
                      or drop/returns/input and wait for the scheduler (or click Scan CCD).
                    </td>
                  </tr>
                )}
              {/* Ledger uploads (CCD files fully processed into payments) */}
              {[...liveUploads]
                .sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at))
                .map((u) => (
                  <tr key={u.upload_id}>
                    <td className="table__mono">{u.file_name}</td>
                    <td>ledger (CCD processed)</td>
                    <td className="table__num">{u.entry_count} entries</td>
                    <td>{formatTimestamp(u.uploaded_at)}</td>
                  </tr>
                ))}
              {/* Drop folder files processed by the scheduler (processed/ or error/) */}
              {dropFiles
                .filter((f) => !liveUploads.some((u) => u.file_name === f.filename))
                .map((f) => (
                  <tr key={`${f.subfolder}/${f.filename}`}>
                    <td className="table__mono">{f.filename}</td>
                    <td>drop/{f.subfolder}</td>
                    <td className="table__num">{f.size_bytes} B</td>
                    <td>{formatTimestamp(f.modified_at)}</td>
                  </tr>
                ))}
              {/* demo-inbox files not yet represented above */}
              {(flowState?.detected_files ?? [])
                .filter(
                  (f) =>
                    !liveUploads.some((u) => u.file_name === f.filename) &&
                    !dropFiles.some((d) => d.filename === f.filename),
                )
                .map((file) => (
                  <tr key={`${file.path}-${file.discovered_at}`}>
                    <td className="table__mono">{file.filename}</td>
                    <td>demo-inbox</td>
                    <td className="table__num">{file.size_bytes} B</td>
                    <td>{formatTimestamp(file.discovered_at)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
