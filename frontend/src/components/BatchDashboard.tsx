import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { BatchSummary, PaymentRecord } from "../types/api";
import { StatusBadge } from "./StatusBadge";

interface BatchDashboardProps {
  onSelectPayment?: (payment: PaymentRecord) => void;
}

export function BatchDashboard({ onSelectPayment }: BatchDashboardProps) {
  const [batches, setBatches] = useState<BatchSummary[]>([]);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [batchFilter, setBatchFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  useEffect(() => {
    let mounted = true;
    Promise.all([api.getBatchDashboard(), api.listPayments()]).then(([b, p]) => {
      if (!mounted) return;
      setBatches(b.rows);
      setPayments(p);
      if (b.rows.length > 0) setBatchFilter(b.rows[0].batchId);
    });
    return () => {
      mounted = false;
    };
  }, []);

  const filtered = useMemo(
    () =>
      payments.filter(
        (p) =>
          (batchFilter === "" || p.batchId === batchFilter) &&
          (statusFilter === "" || p.currentStatus === statusFilter),
      ),
    [payments, batchFilter, statusFilter],
  );

  return (
    <section className="card">
      <header className="card__header">
        <h2 className="card__title">Batch dashboard</h2>
        <p className="card__subtitle">
          Payments grouped by batch and cycle. Filter by batch or status to
          focus on a specific slice. Settlement records are summary evidence,
          not payment-level clearing evidence.
        </p>
      </header>

      <div className="batch-summary">
        {batches.map((b) => (
          <button
            type="button"
            key={b.batchId}
            className={
              "batch-summary__card" +
              (batchFilter === b.batchId ? " batch-summary__card--active" : "")
            }
            onClick={() => setBatchFilter(b.batchId)}
          >
            <div className="batch-summary__head">
              <span className="batch-summary__time">{b.cycleTime}</span>
              <span className="batch-summary__file">{b.sourceFile}</span>
            </div>
            <div className="batch-summary__id">{b.batchId}</div>
            <div className="batch-summary__metrics">
              <span>{b.paymentCount} total</span>
              <span className="text-info">{b.sentToScheme} sent to scheme</span>
              <span className="text-warn">{b.withBeneficiaryBank} with beneficiary bank</span>
              <span className="text-danger">{b.rejectedByScheme} rejected by scheme</span>
              <span className="text-danger-2">
                {b.rejectedByBeneficiaryBank} rejected by beneficiary bank
              </span>
            </div>
          </button>
        ))}
      </div>

      <div className="filter-row">
        <label className="field field--inline">
          <span className="field__label">Batch</span>
          <select
            className="field__control"
            value={batchFilter}
            onChange={(e) => setBatchFilter(e.target.value)}
          >
            <option value="">All batches</option>
            {batches.map((b) => (
              <option key={b.batchId} value={b.batchId}>
                {b.cycleTime} — {b.batchId}
              </option>
            ))}
          </select>
        </label>
        <label className="field field--inline">
          <span className="field__label">Status</span>
          <select
            className="field__control"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="WITH BANK">WITH BANK</option>
            <option value="SENT TO SCHEME">SENT TO SCHEME</option>
            <option value="WITH BENEFICIARY BANK">WITH BENEFICIARY BANK</option>
            <option value="REJECTED BY SCHEME">REJECTED BY SCHEME</option>
            <option value="REJECTED BY BENEFICIARY BANK">
              REJECTED BY BENEFICIARY BANK
            </option>
          </select>
        </label>
        <div className="filter-row__spacer" />
        <span className="filter-row__count">
          Showing {filtered.length} of {payments.length}
        </span>
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Trace</th>
              <th>Customer</th>
              <th>Beneficiary</th>
              <th className="table__num">Amount</th>
              <th>Status</th>
              <th>Return</th>
              <th>Risk</th>
              <th className="table__action">Detail</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => (
              <tr key={p.paymentId}>
                <td>
                  <div className="table__mono">{p.traceNumber}</div>
                  <div className="table__sub">{p.paymentId}</div>
                </td>
                <td>
                  <div>{p.customerName}</div>
                  <div className="table__sub">{p.customerId}</div>
                </td>
                <td>{p.beneficiaryName}</td>
                <td className="table__num">${p.amount.toFixed(2)}</td>
                <td>
                  <StatusBadge status={p.currentStatus} size="sm" />
                </td>
                <td>{p.returnReasonCode ?? "—"}</td>
                <td>
                  <span className={`risk risk--${p.riskLevel.toLowerCase()}`}>
                    {p.riskLevel}
                  </span>
                </td>
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
        Each status has an evidence explanation. Open payment detail to review
        settlement summary, scheme reject, and return-file sources.
      </p>
    </section>
  );
}
