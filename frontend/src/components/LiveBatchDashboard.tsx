import { useCallback, useEffect, useMemo, useState } from "react";
import {
  LEDGER_STATUS_ORDER,
  countByStatus,
  fetchLiveLedger,
  formatDollars,
  formatTimestamp,
  groupByBatch,
  latestEvidenceSummary,
  sortPaymentsByPaymentId,
} from "../api/ledger";
import type { PaymentLedgerView } from "../types/api";
import { StatusBadge } from "./StatusBadge";

const EMPTY_STATE_MESSAGE =
  "No live ledger payments yet. Go to Demo Simulator, switch Demo Mode OFF, seed CCD files, then click Scan CCD.";

const LIVE_MODE_SUBTITLE =
  "Live backend ledger from parsed CCD and file evidence. Settlement summary is not payment-level clearing evidence.";

export function LiveBatchDashboard() {
  const [ledger, setLedger] = useState<PaymentLedgerView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedBatch, setSelectedBatch] = useState<string>("");

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const view = await fetchLiveLedger();
      setLedger(view);
      setError(null);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to load live payment ledger.",
      );
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const payments = ledger?.payments ?? [];
  const groups = useMemo(() => groupByBatch(payments), [payments]);
  const totalCounts = useMemo(() => countByStatus(payments), [payments]);
  const batchRows = useMemo(
    () =>
      groups.map((group) => ({
        ...group,
        batchRisk:
          group.payments.find((p) => p.current_batch_risk_classification)
            ?.current_batch_risk_classification ?? null,
      })),
    [groups],
  );

  useEffect(() => {
    if (groups.length === 0) {
      if (selectedBatch !== "") setSelectedBatch("");
      return;
    }
    if (!batchRows.some((g) => g.batchKey === selectedBatch)) {
      setSelectedBatch(batchRows[0].batchKey);
    }
  }, [batchRows, groups.length, selectedBatch]);

  const activeGroup = batchRows.find((g) => g.batchKey === selectedBatch) ?? null;
  const activePayments = activeGroup
    ? sortPaymentsByPaymentId(activeGroup.payments)
    : [];

  return (
    <section className="card">
      <header className="card__header card__header--split">
        <div>
          <p className="live-ledger__mode-label">
            Live backend ledger from parsed CCD and file evidence
          </p>
          <h2 className="card__title">Batch dashboard</h2>
          <p className="card__subtitle">{LIVE_MODE_SUBTITLE}</p>
        </div>
        <div className="live-ledger__actions">
          {ledger && (
            <div className="live-ledger__asof">
              As of {formatTimestamp(ledger.as_of)}
            </div>
          )}
          <button
            type="button"
            className="button button--ghost"
            disabled={isRefreshing}
            onClick={() => void refresh()}
          >
            {isRefreshing ? "Refreshing…" : "Refresh ledger"}
          </button>
        </div>
      </header>

      {error && <div className="local-flow__error">{error}</div>}

      <div className="live-ledger__counts">
        {LEDGER_STATUS_ORDER.map((status) => (
          <div key={status} className="local-flow__ledger-count">
            <StatusBadge status={status} size="sm" />
            <span className="local-flow__ledger-count-value">
              {totalCounts[status]}
            </span>
          </div>
        ))}
      </div>

      <p className="table__note">
        AI risk classification uses deterministic ledger evidence, demo
        customer history, and available CCD validation findings. It does not
        determine payment status, credit risk, or fraud risk.
      </p>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Batch Key</th>
              <th>Source File</th>
              <th>Batch Risk Band</th>
              <th>Risk Score</th>
              <th>Confidence Score</th>
              <th>Validation Findings</th>
              <th>Summary</th>
              <th>Recommendation</th>
              <th>Total Payments</th>
              <th>Status Counts</th>
              <th className="table__action">Context</th>
            </tr>
          </thead>
          <tbody>
            {batchRows.length === 0 && (
              <tr>
                <td colSpan={11} className="table__empty">
                  {EMPTY_STATE_MESSAGE}
                </td>
              </tr>
            )}
            {batchRows.map((batch) => (
              <tr
                key={batch.batchKey}
                className={
                  selectedBatch === batch.batchKey ? "table__row-selected" : ""
                }
              >
                <td className="table__mono">{batch.batchKey}</td>
                <td>
                  <span className="table__mono">{batch.sourceFile}</span>
                </td>
                <td>
                  {batch.batchRisk ? (
                    <span
                      className={
                        "ai-risk-badge ai-risk-badge--" +
                        batch.batchRisk.risk_band.toLowerCase()
                      }
                    >
                      {batch.batchRisk.risk_band}
                    </span>
                  ) : (
                    <span className="table__subtle">N/A</span>
                  )}
                </td>
                <td>
                  {batch.batchRisk
                    ? `${batch.batchRisk.risk_score}/100`
                    : "N/A"}
                </td>
                <td>
                  {batch.batchRisk
                    ? `${batch.batchRisk.confidence_score}/100`
                    : "N/A"}
                </td>
                <td className="live-ledger__evidence">
                  {batch.batchRisk && batch.batchRisk.validation_findings.length > 0 ? (
                    <ul className="table__list-compact">
                      {batch.batchRisk.validation_findings.slice(0, 2).map((finding, idx) => (
                        <li key={idx}>{finding}</li>
                      ))}
                    </ul>
                  ) : (
                    "No validation findings"
                  )}
                </td>
                <td className="live-ledger__evidence">
                  {batch.batchRisk
                    ? batch.batchRisk.summary
                    : "N/A"}
                </td>
                <td className="live-ledger__evidence">
                  {batch.batchRisk
                    ? batch.batchRisk.recommendation
                    : "N/A"}
                </td>
                <td className="table__mono">
                  {batch.payments.length}
                </td>
                <td className="live-ledger__evidence">
                  {batch.counts["WITH BANK"]} with bank · {batch.counts["SENT TO SCHEME"]} sent to scheme · {batch.counts["WITH BENEFICIARY BANK"]} with beneficiary bank · {batch.counts["REJECTED BY SCHEME"]} rejected by scheme · {batch.counts["REJECTED BY BENEFICIARY BANK"]} rejected by beneficiary bank
                </td>
                <td className="table__action">
                  <button
                    type="button"
                    className="button button--link"
                    onClick={() => setSelectedBatch(batch.batchKey)}
                  >
                    Payments
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="live-detail__section">
        <h3 className="live-detail__section-title">
          Batch Payment Context {activeGroup ? `- ${activeGroup.batchKey}` : ""}
        </h3>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Payment ID</th>
                <th>Trace Number</th>
                <th>Individual Name</th>
                <th>Individual ID</th>
                <th className="table__num">Amount</th>
                <th>Status</th>
                <th>Latest Evidence</th>
              </tr>
            </thead>
            <tbody>
              {activePayments.length === 0 && (
                <tr>
                  <td colSpan={7} className="table__empty">
                    Select a batch to view payment context.
                  </td>
                </tr>
              )}
              {activePayments.map((payment) => (
                <tr key={payment.payment_id}>
                  <td className="table__mono">{payment.payment_id}</td>
                  <td className="table__mono">{payment.trace_number}</td>
                  <td>{payment.individual_name}</td>
                  <td className="table__mono">{payment.individual_id_number}</td>
                  <td className="table__num">{formatDollars(payment.amount_cents)}</td>
                  <td>
                    <StatusBadge status={payment.current_status} size="sm" />
                  </td>
                  <td className="live-ledger__evidence">{latestEvidenceSummary(payment)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <p className="table__note">
        Settlement summary evidence is aggregate only; no payment-level
        clearing is claimed. A payment remaining with the beneficiary bank
        may still be returned in a later cycle.
      </p>
    </section>
  );
}
