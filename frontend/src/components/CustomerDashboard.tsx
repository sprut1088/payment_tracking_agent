import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { CustomerSummary, PaymentRecord } from "../types/api";
import { StatusBadge } from "./StatusBadge";

interface CustomerDashboardProps {
  onSelectPayment?: (payment: PaymentRecord) => void;
}

export function CustomerDashboard({ onSelectPayment }: CustomerDashboardProps) {
  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [selected, setSelected] = useState<string>("");

  useEffect(() => {
    let mounted = true;
    Promise.all([api.getCustomerDashboard(), api.listPayments()]).then(
      ([c, p]) => {
        if (!mounted) return;
        setCustomers(c.rows);
        setPayments(p);
        if (c.rows.length > 0) setSelected(c.rows[0].customerId);
      },
    );
    return () => {
      mounted = false;
    };
  }, []);

  const rows = useMemo(
    () => payments.filter((p) => (selected ? p.customerId === selected : true)),
    [payments, selected],
  );

  return (
    <section className="card">
      <header className="card__header">
        <h2 className="card__title">Customer dashboard</h2>
        <p className="card__subtitle">
          All payments for a customer across batches and dates.
        </p>
      </header>

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
              <span>{c.totalPayments} total</span>
              <span className="text-success">{c.cleared} cleared</span>
              <span className="text-warn">{c.withBeneficiaryBank} held</span>
              <span className="text-danger">{c.rejected} rejected</span>
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
    </section>
  );
}
