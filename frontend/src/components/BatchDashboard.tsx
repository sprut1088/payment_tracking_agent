import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { BatchSummary, PaymentRecord, UnderReviewItem } from "../types/api";
import { CcdReviewPanel } from "./CcdReviewPanel";
import { StatusBadge } from "./StatusBadge";

interface BatchDashboardProps {
  onSelectPayment?: (payment: PaymentRecord) => void;
  demoMode: boolean;
  refreshKey?: number;
}

export function BatchDashboard({ onSelectPayment, demoMode, refreshKey }: BatchDashboardProps) {
  const [batches, setBatches] = useState<BatchSummary[]>([]);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [reviewItems, setReviewItems] = useState<UnderReviewItem[]>([]);
  const [batchFilter, setBatchFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const prevDemoModeRef = useRef(demoMode);

  const loadData = () => {
    setError(null);
    const batchCall = demoMode ? api.getBatchDashboard() : api.getBatchDashboardLive();
    const paymentsCall = demoMode ? api.listPayments() : api.listPaymentsLive();
    const reviewCall = demoMode
      ? Promise.resolve([] as UnderReviewItem[])
      : api.getUnderReview();
    return Promise.all([batchCall, paymentsCall, reviewCall]);
  };

  useEffect(() => {
    let mounted = true;
    setError(null);
    // Only clear data when demoMode flips (mock ↔ live are incompatible).
    // When refreshKey increments (revisiting the page), keep existing rows
    // visible while the background re-fetch completes.
    const modeChanged = prevDemoModeRef.current !== demoMode;
    prevDemoModeRef.current = demoMode;
    if (modeChanged) {
      setBatches([]);
      setPayments([]);
      setReviewItems([]);
    }
    loadData()
      .then(([b, p, r]) => {
        if (!mounted) return;
        setBatches(b.rows);
        setPayments(p);
        setReviewItems(r);
        if (b.rows.length > 0) setBatchFilter(b.rows[0].batchId);
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
      loadData()
        .then(([b, p, r]) => {
          setBatches(b.rows);
          setPayments(p);
          setReviewItems(r);
        })
        .catch(() => undefined);
    }, 30_000);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demoMode]);

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
    <>
      {/* Review queue shown only in Live Folder Mode when there are items to review */}
      {!demoMode && (
        <CcdReviewPanel
          items={reviewItems}
          onReviewed={() => {
            // Refresh all data after accept or reject
            loadData()
              .then(([b, p, r]) => {
                setBatches(b.rows);
                setPayments(p);
                setReviewItems(r);
                if (b.rows.length > 0 && batchFilter === "") setBatchFilter(b.rows[0].batchId);
              })
              .catch(() => undefined);
          }}
        />
      )}

      <section className="card">
        <header className="card__header">
          <h2 className="card__title">Batch dashboard</h2>
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
            <div className="batch-summary__risk-row">
              <span
                className={`risk risk--${b.fileRiskLevel.toLowerCase()}`}
                data-tooltip={b.fileRiskReason}
              >
                {b.fileRiskLevel} risk
              </span>
              <span className={b.rejectedPercentage > 0 ? "text-danger" : "text-success"}>
                {b.rejectedPercentage.toFixed(1)}% rejected
              </span>
            </div>
            <div className="batch-summary__metrics">
              <span>{b.paymentCount} Total</span>
              <span>{b.withBank} With Bank</span>
              <span className="text-info">{b.sentToScheme} Sent to Scheme</span>
              <span className="text-warn">{b.withBeneficiaryBank} With Beneficiary Bank</span>
              <span className="text-danger">{b.rejectedByScheme} Rejected by Scheme</span>
              <span className="text-danger-2">
                {b.rejectedByBeneficiaryBank} Rejected by Beneficiary Bank
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
    </>
  );
}
