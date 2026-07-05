import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { CustomerSummary, PaymentRecord } from "../types/api";
import { StatusBadge } from "./StatusBadge";

interface CustomerDashboardProps {
  onSelectPayment?: (payment: PaymentRecord) => void;
  demoMode: boolean;
  refreshKey?: number;
}

export function CustomerDashboard({ onSelectPayment, demoMode, refreshKey }: CustomerDashboardProps) {
  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const prevDemoModeRef = useRef(demoMode);

  useEffect(() => {
    let mounted = true;
    setError(null);
    // Only clear data when demoMode flips (mock ↔ live are incompatible).
    // When refreshKey increments (revisiting the page), keep existing rows
    // visible while the background re-fetch completes.
    const modeChanged = prevDemoModeRef.current !== demoMode;
    prevDemoModeRef.current = demoMode;
    if (modeChanged) {
      setCustomers([]);
      setPayments([]);
    }
    const customerCall = demoMode ? api.getCustomerDashboard() : api.getCustomerDashboardLive();
    const paymentsCall = demoMode ? api.listPayments() : api.listPaymentsLive();
    Promise.all([customerCall, paymentsCall])
      .then(([c, p]) => {
        if (!mounted) return;
        setCustomers(c.rows);
        setPayments(p);
        if (c.rows.length > 0) setSelected(c.rows[0].customerId);
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load payments from backend.");
      });
    return () => {
      mounted = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demoMode, refreshKey]);

  // Auto-refresh every 30 s in live mode so scheduler-driven status changes appear
  // without requiring the user to navigate away and back.
  useEffect(() => {
    if (demoMode) return;
    const id = setInterval(() => {
      const customerCall = api.getCustomerDashboardLive();
      const paymentsCall = api.listPaymentsLive();
      Promise.all([customerCall, paymentsCall])
        .then(([c, p]) => {
          setCustomers(c.rows);
          setPayments(p);
        })
        .catch(() => undefined);
    }, 30_000);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demoMode]);

  const rows = useMemo(
    () => payments.filter((p) => (selected ? p.customerId === selected : true)),
    [payments, selected],
  );

  return (
    <section className="card">
      <header className="card__header">
        <h2 className="card__title">Customer dashboard</h2>
        <p className="card__subtitle">
          {demoMode
            ? "Demo Mode ON — predefined SME-aligned mock data."
            : "Live Folder Mode — data loaded from backend payment ledger."}
        </p>
      </header>

      {error && (
        <div className="card__error">
          Backend error: {error}
        </div>
      )}

      <div className="customer-grid">
        {customers.map((c) => (
          <button
            type="button"
            key={c.customerId}
            className={
              "customer-card" +
              (selected === c.customerId ? " customer-card--active" : "")
            }
            onClick={() => setSelected(c.customerId)}
          >
            <div className="customer-card__name">{c.customerName}</div>
            <div className="customer-card__id">{c.customerId}</div>
            <div className="customer-card__metrics">
              <span>{c.totalPayments} Total</span>
              <span>{c.withBank} With Bank</span>
              <span className="text-info">{c.sentToScheme} Sent to Scheme</span>
              <span className="text-warn">{c.withBeneficiaryBank} With Beneficiary Bank</span>
              <span className="text-danger">{c.rejectedByScheme} Rejected by Scheme</span>
              <span className="text-danger-2">
                {c.rejectedByBeneficiaryBank} Rejected by Beneficiary Bank
              </span>
            </div>
            <div className="customer-card__history">
              Historical rejections: <strong>{c.historicalRejectionCount}</strong>
              {c.lastRejectionDate && <> · last {c.lastRejectionDate}</>}
            </div>
          </button>
        ))}
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Payment</th>
              <th>Batch</th>
              <th>Beneficiary</th>
              <th className="table__num">Amount</th>
              <th>Status</th>
              <th>Return</th>
              <th className="table__action">Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.paymentId}>
                <td>
                  <div className="table__mono">{p.traceNumber}</div>
                  <div className="table__sub">{p.paymentId}</div>
                </td>
                <td>
                  <div>{p.batchId}</div>
                  <div className="table__sub">{p.cycleTime}</div>
                </td>
                <td>{p.beneficiaryName}</td>
                <td className="table__num">${p.amount.toFixed(2)}</td>
                <td>
                  <StatusBadge status={p.currentStatus} size="sm" />
                </td>
                <td>{p.returnReasonCode ?? "—"}</td>
                <td className="table__action">
                  <button
                    type="button"
                    className="button button--link"
                    onClick={() => onSelectPayment?.(p)}
                  >
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="table__note">
        Use payment detail to see the evidence explanation behind each status.
      </p>
    </section>
  );
}
