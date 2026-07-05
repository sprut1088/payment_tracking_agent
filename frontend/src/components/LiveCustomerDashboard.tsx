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
  "No live ledger payments yet. Go to Demo Simulator, switch Demo Mode OFF, seed CCD files, then click Scan CCD.";

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
  const customerRows = useMemo(
    () =>
      groups.map((group) => ({
        ...group,
        customerRisk:
          group.payments.find((p) => p.current_customer_risk_classification)
            ?.current_customer_risk_classification ?? null,
      })),
    [groups],
  );

  useEffect(() => {
    if (customerRows.length === 0) {
      if (selectedKey !== "") setSelectedKey("");
      return;
    }
    const first = customerKey(
      customerRows[0].individualId,
      customerRows[0].individualName,
    );
    if (
      !customerRows.some(
        (g) => customerKey(g.individualId, g.individualName) === selectedKey,
      )
    ) {
      setSelectedKey(first);
    }
  }, [customerRows, selectedKey]);

  const activeGroup =
    customerRows.find(
      (g) => customerKey(g.individualId, g.individualName) === selectedKey,
    ) ?? null;
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
          <h2 className="card__title">Customer dashboard</h2>
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
              <th>Customer ID</th>
              <th>Customer Name</th>
              <th>Customer Risk Band</th>
              <th>Risk Score</th>
              <th>Confidence Score</th>
              <th>Recent rejection counts</th>
              <th>Summary</th>
              <th>Recommendation</th>
              <th>Status Counts</th>
              <th className="table__action">Context</th>
            </tr>
          </thead>
          <tbody>
            {customerRows.length === 0 && (
              <tr>
                <td colSpan={10} className="table__empty">
                  {EMPTY_STATE_MESSAGE}
                </td>
              </tr>
            )}
            {customerRows.map((customer) => {
              const key = customerKey(customer.individualId, customer.individualName);
              return (
              <tr
                key={key}
                className={selectedKey === key ? "table__row-selected" : ""}
              >
                <td className="table__mono">{customer.individualId}</td>
                <td>{customer.individualName}</td>
                <td>
                  {customer.customerRisk ? (
                    <span
                      className={
                        "ai-risk-badge ai-risk-badge--" +
                        customer.customerRisk.risk_band.toLowerCase()
                      }
                    >
                      {customer.customerRisk.risk_band}
                    </span>
                  ) : (
                    <span className="table__subtle">N/A</span>
                  )}
                </td>
                <td>
                  {customer.customerRisk
                    ? `${customer.customerRisk.risk_score}/100`
                    : "N/A"}
                </td>
                <td>
                  {customer.customerRisk
                    ? `${customer.customerRisk.confidence_score}/100`
                    : "N/A"}
                </td>
                <td className="live-ledger__evidence">
                  {customer.customerRisk
                    ? customer.customerRisk.evidence_used.find((item) =>
                        item.toLowerCase().includes("rejection counts"),
                      ) ??
                      "No count summary"
                    : "N/A"}
                </td>
                <td className="live-ledger__evidence">
                  {customer.customerRisk
                    ? customer.customerRisk.summary
                    : "N/A"}
                </td>
                <td className="live-ledger__evidence">
                  {customer.customerRisk
                    ? customer.customerRisk.recommendation
                    : "N/A"}
                </td>
                <td className="live-ledger__evidence">
                  {customer.counts["WITH BANK"]} with bank · {customer.counts["SENT TO SCHEME"]} sent to scheme · {customer.counts["WITH BENEFICIARY BANK"]} with beneficiary bank · {customer.counts["REJECTED BY SCHEME"]} rejected by scheme · {customer.counts["REJECTED BY BENEFICIARY BANK"]} rejected by beneficiary bank
                </td>
                <td className="table__action">
                  <button
                    type="button"
                    className="button button--link"
                    onClick={() => setSelectedKey(key)}
                  >
                    Payments
                  </button>
                </td>
              </tr>
            )})}
          </tbody>
        </table>
      </div>

      <section className="live-detail__section">
        <h3 className="live-detail__section-title">
          Customer Payment Context {activeGroup ? `- ${activeGroup.individualName}` : ""}
        </h3>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Payment ID</th>
                <th>Trace Number</th>
                <th>Batch Key</th>
                <th className="table__num">Amount</th>
                <th>Status</th>
                <th>Latest Evidence</th>
              </tr>
            </thead>
            <tbody>
              {activePayments.length === 0 && (
                <tr>
                  <td colSpan={6} className="table__empty">
                    Select a customer to view payment context.
                  </td>
                </tr>
              )}
              {activePayments.map((payment) => (
                <tr key={payment.payment_id}>
                  <td className="table__mono">{payment.payment_id}</td>
                  <td className="table__mono">{payment.trace_number}</td>
                  <td className="table__mono">{payment.batch_key}</td>
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
        Customer-level view groups by parsed individual ID and name from CCD
        entry-detail records. No payment-level clearing is claimed from
        settlement summary evidence.
      </p>
    </section>
  );
}
