import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { StatusBadge } from "./StatusBadge";
import type {
  DemoFlowBatch,
  DemoFlowBatchStatus,
  DemoFlowConfig,
  DemoFlowScanResult,
  DemoFlowState,
  LedgerPayment,
  LedgerPaymentStatus,
  PaymentLedgerView,
  SettlementSchemeEvidenceStatus,
} from "../types/api";

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatDollars(amountCents: number): string {
  return (amountCents / 100).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
  });
}

function latestEvidenceSummary(payment: LedgerPayment): string {
  const history = payment.status_history;
  if (history.length > 0) return history[history.length - 1].evidence.summary;
  const evidence = payment.evidence;
  if (evidence.length > 0) return evidence[evidence.length - 1].summary;
  return "";
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

function sortPaymentsByPaymentId(rows: LedgerPayment[]): LedgerPayment[] {
  return [...rows].sort((a, b) => a.payment_id.localeCompare(b.payment_id));
}

const LEDGER_STATUS_ORDER: LedgerPaymentStatus[] = [
  "WITH BANK",
  "SENT TO SCHEME",
  "WITH BENEFICIARY BANK",
  "REJECTED BY SCHEME",
  "REJECTED BY BENEFICIARY BANK",
];

export function LocalFolderDemoControls() {
  const [config, setConfig] = useState<DemoFlowConfig | null>(null);
  const [flowState, setFlowState] = useState<DemoFlowState | null>(null);
  const [ledger, setLedger] = useState<PaymentLedgerView | null>(null);
  const [lastScan, setLastScan] = useState<DemoFlowScanResult | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const refreshPayments = useCallback(async () => {
    const view = await api.getDemoFlowPayments();
    setLedger(view);
  }, []);

  const refresh = useCallback(async () => {
    const [cfg, state, payments] = await Promise.all([
      api.getDemoFlowConfig(),
      api.getDemoFlowState(),
      api.getDemoFlowPayments(),
    ]);
    setConfig(cfg);
    setFlowState(state);
    setLedger(payments);
  }, []);

  useEffect(() => {
    let mounted = true;
    Promise.all([
      api.getDemoFlowConfig(),
      api.getDemoFlowState(),
      api.getDemoFlowPayments(),
    ])
      .then(([cfg, state, payments]) => {
        if (!mounted) return;
        setConfig(cfg);
        setFlowState(state);
        setLedger(payments);
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
      returnEvidenceReceived: batches.filter(
        (b) => b.status === "RETURN_EVIDENCE_RECEIVED",
      ).length,
      detectedFiles: flowState?.detected_files.length ?? 0,
    };
  }, [flowState]);

  const ledgerPayments = useMemo(
    () => sortPaymentsByPaymentId(ledger?.payments ?? []),
    [ledger?.payments],
  );

  const ledgerCounts = useMemo(() => {
    const counts: Record<LedgerPaymentStatus, number> = {
      "WITH BANK": 0,
      "SENT TO SCHEME": 0,
      "WITH BENEFICIARY BANK": 0,
      "REJECTED BY SCHEME": 0,
      "REJECTED BY BENEFICIARY BANK": 0,
    };
    for (const payment of ledger?.payments ?? []) {
      counts[payment.current_status] += 1;
    }
    return counts;
  }, [ledger?.payments]);

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
              await refreshPayments();
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
              await refreshPayments();
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
              await refreshPayments();
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
        <div className="local-flow__ledger-header">
          <h3 className="local-flow__section-title">Live Payment Ledger</h3>
          <button
            type="button"
            className="button button--ghost"
            disabled={isBusy}
            onClick={() =>
              void runAction("Live ledger refreshed", async () => {
                await refreshPayments();
              })
            }
          >
            Refresh payments
          </button>
        </div>
        <p className="local-flow__section-subtitle">
          Live backend ledger from parsed CCD and file evidence. Settlement
          summary is not payment-level clearing evidence; no payment is marked
          cleared.
        </p>

        <div className="local-flow__ledger-counts">
          {LEDGER_STATUS_ORDER.map((status) => (
            <div key={status} className="local-flow__ledger-count">
              <StatusBadge status={status} size="sm" />
              <span className="local-flow__ledger-count-value">
                {ledgerCounts[status]}
              </span>
            </div>
          ))}
          {ledger && (
            <div className="local-flow__ledger-asof">
              As of {formatTimestamp(ledger.as_of)}
            </div>
          )}
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Payment ID</th>
                <th>Trace number</th>
                <th>Individual name</th>
                <th>Individual ID</th>
                <th className="table__num">Amount</th>
                <th>Current status</th>
                <th>Latest evidence</th>
              </tr>
            </thead>
            <tbody>
              {ledgerPayments.length === 0 && (
                <tr>
                  <td colSpan={7} className="table__empty">
                    No live ledger payments yet. Seed CCD files, then click
                    Scan CCD.
                  </td>
                </tr>
              )}
              {ledgerPayments.map((payment) => (
                <tr key={payment.payment_id}>
                  <td className="table__mono">{payment.payment_id}</td>
                  <td className="table__mono">{payment.trace_number}</td>
                  <td>{payment.individual_name}</td>
                  <td className="table__mono">{payment.individual_id_number}</td>
                  <td className="table__num">
                    {formatDollars(payment.amount_cents)}
                  </td>
                  <td>
                    <StatusBadge status={payment.current_status} size="sm" />
                  </td>
                  <td className="local-flow__ledger-evidence">
                    {latestEvidenceSummary(payment)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

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
