import { useCallback, useEffect, useMemo, useState } from "react";
import {
  LEDGER_STATUS_ORDER,
  countByStatus,
  fetchLiveLedger,
  formatDollars,
  formatTimestamp,
  groupByCustomer,
  latestEvidenceSummary,
  sortPaymentsByPaymentId,
} from "../api/ledger";
import type { PaymentLedgerView } from "../types/api";
import { StatusBadge } from "./StatusBadge";

const EMPTY_STATE_MESSAGE =
  "No live ledger payments yet. Go to Demo Simulator, seed CCD files, then click Scan CCD.";

const LIVE_MODE_SUBTITLE =
  "Live backend ledger from parsed CCD and file evidence. Settlement summary is not payment-level clearing evidence.";

function customerKey(id: string, name: string): string {
  return `${id}||${name}`;
}

export function LiveCustomerDashboard() {
  const [ledger, setLedger] = useState<PaymentLedgerView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string>("");

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
  const groups = useMemo(() => groupByCustomer(payments), [payments]);
  const totalCounts = useMemo(() => countByStatus(payments), [payments]);

  useEffect(() => {
    if (groups.length === 0) {
      if (selectedKey !== "") setSelectedKey("");
      return;
    }
    const first = customerKey(groups[0].individualId, groups[0].individualName);
    if (
      !groups.some(
        (g) => customerKey(g.individualId, g.individualName) === selectedKey,
      )
    ) {
      setSelectedKey(first);
    }
  }, [groups, selectedKey]);

  const activeGroup =
    groups.find(
      (g) => customerKey(g.individualId, g.individualName) === selectedKey,
    ) ?? null;
  const activePayments = activeGroup
    ? sortPaymentsByPaymentId(activeGroup.payments)
    : [];

  return (
    <section className="card">
      <header className="card__header card__header--split">
        <div>
          <h2 className="card__title">Customer dashboard</h2>
          <p className="card__subtitle">{LIVE_MODE_SUBTITLE}</p>
          <p className="live-ledger__mode-label">
            Live backend ledger from parsed CCD and file evidence
          </p>
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

      <div className="customer-grid">
        {groups.map((group) => {
          const key = customerKey(group.individualId, group.individualName);
          return (
            <button
              type="button"
              key={key}
              className={
                "customer-card" +
                (selectedKey === key ? " customer-card--active" : "")
              }
              onClick={() => setSelectedKey(key)}
            >
              <div className="customer-card__name">{group.individualName}</div>
              <div className="customer-card__id">{group.individualId}</div>
              <div className="customer-card__metrics">
                <span>{group.payments.length} total</span>
                <span className="text-info">
                  {group.counts["SENT TO SCHEME"]} sent to scheme
                </span>
                <span className="text-warn">
                  {group.counts["WITH BENEFICIARY BANK"]} with beneficiary bank
                </span>
                <span className="text-danger">
                  {group.counts["REJECTED BY SCHEME"]} rejected by scheme
                </span>
                <span className="text-danger-2">
                  {group.counts["REJECTED BY BENEFICIARY BANK"]} rejected by
                  beneficiary bank
                </span>
              </div>
            </button>
          );
        })}
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Individual ID</th>
              <th>Individual name</th>
              <th>Payment ID</th>
              <th>Trace number</th>
              <th>Batch key</th>
              <th className="table__num">Amount</th>
              <th>Current status</th>
              <th>Latest evidence</th>
            </tr>
          </thead>
          <tbody>
            {activePayments.length === 0 && (
              <tr>
                <td colSpan={8} className="table__empty">
                  {EMPTY_STATE_MESSAGE}
                </td>
              </tr>
            )}
            {activePayments.map((payment) => (
              <tr key={payment.payment_id}>
                <td className="table__mono">{payment.individual_id_number}</td>
                <td>{payment.individual_name}</td>
                <td className="table__mono">{payment.payment_id}</td>
                <td className="table__mono">{payment.trace_number}</td>
                <td className="table__mono">{payment.batch_key}</td>
                <td className="table__num">
                  {formatDollars(payment.amount_cents)}
                </td>
                <td>
                  <StatusBadge status={payment.current_status} size="sm" />
                </td>
                <td className="live-ledger__evidence">
                  {latestEvidenceSummary(payment)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="table__note">
        Customer-level view groups by parsed individual ID and name from CCD
        entry-detail records. No payment-level clearing is claimed from
        settlement summary evidence.
      </p>
    </section>
  );
}
