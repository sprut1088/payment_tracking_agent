import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  DemoFlowBatch,
  DemoFlowConfig,
  DemoFlowScanResult,
  DemoFlowState,
  SettlementSchemeEvidenceStatus,
} from "../types/api";

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
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

export function LocalFolderDemoControls() {
  const [config, setConfig] = useState<DemoFlowConfig | null>(null);
  const [flowState, setFlowState] = useState<DemoFlowState | null>(null);
  const [lastScan, setLastScan] = useState<DemoFlowScanResult | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [cfg, state] = await Promise.all([
      api.getDemoFlowConfig(),
      api.getDemoFlowState(),
    ]);
    setConfig(cfg);
    setFlowState(state);
  }, []);

  useEffect(() => {
    let mounted = true;
    Promise.all([api.getDemoFlowConfig(), api.getDemoFlowState()])
      .then(([cfg, state]) => {
        if (!mounted) return;
        setConfig(cfg);
        setFlowState(state);
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load demo-flow state.");
      });
    return () => {
      mounted = false;
    };
  }, []);

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
    const batches = flowState?.batches ?? [];
    return {
      totalBatches: batches.length,
      awaitingSettlement: batches.filter((b) => b.status === "AWAITING_SETTLEMENT").length,
      awaitingReturns: batches.filter((b) => b.status === "AWAITING_RETURNS").length,
      complete: batches.filter((b) => b.status === "COMPLETE").length,
      detectedFiles: flowState?.detected_files.length ?? 0,
    };
  }, [flowState]);

  return (
    <section className="card">
      <header className="card__header">
        <h2 className="card__title">Local folder demo flow controls</h2>
        <p className="card__subtitle">
          Drive backend endpoints for folder setup and phased scanning: CCD,
          settlement/scheme reject, then returns.
        </p>
      </header>

      <div className="action-row">
        <button
          type="button"
          className="button button--primary"
          disabled={isBusy}
          onClick={() =>
            void runAction("Folders ensured", async () => {
              const cfg = await api.ensureDemoFlowFolders();
              setConfig(cfg);
              await refresh();
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
              setFlowState(await api.getDemoFlowState());
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
              setFlowState(await api.getDemoFlowState());
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
              setFlowState(await api.getDemoFlowState());
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
              await refresh();
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
              await refresh();
            })
          }
        >
          Reset
        </button>
      </div>

      {message && <div className="local-flow__notice">{message}</div>}
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
          <div className="local-flow__stat-label">Awaiting returns</div>
          <div className="local-flow__stat-value">{summary.awaitingReturns}</div>
        </div>
        <div className="local-flow__stat">
          <div className="local-flow__stat-label">Complete</div>
          <div className="local-flow__stat-value">{summary.complete}</div>
        </div>
        <div className="local-flow__stat">
          <div className="local-flow__stat-label">Detected files</div>
          <div className="local-flow__stat-value">{summary.detectedFiles}</div>
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
                    No batches yet. Place a CCD file in the configured ccd folder,
                    then run Scan CCD.
                  </td>
                </tr>
              )}
              {sortedBatches.map((batch) => (
                <tr key={batch.batch_id}>
                  <td className="table__mono">{batch.batch_id}</td>
                  <td>{batch.status}</td>
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
      </div>

      <div className="local-flow__section">
        <h3 className="local-flow__section-title">Detected files</h3>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Kind</th>
                <th className="table__num">Size (bytes)</th>
                <th>Discovered</th>
              </tr>
            </thead>
            <tbody>
              {(flowState?.detected_files ?? []).length === 0 && (
                <tr>
                  <td colSpan={4} className="table__empty">
                    No files detected yet.
                  </td>
                </tr>
              )}
              {(flowState?.detected_files ?? []).map((file) => (
                <tr key={`${file.path}-${file.discovered_at}`}>
                  <td>{file.filename}</td>
                  <td>{file.kind}</td>
                  <td className="table__num">{file.size_bytes}</td>
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
