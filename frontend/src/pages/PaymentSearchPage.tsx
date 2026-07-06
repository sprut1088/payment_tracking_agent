import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { PaymentDetailDrawer } from "../components/PaymentDetailDrawer";
import { StatusBadge } from "../components/StatusBadge";
import type { BusinessStatus, PaymentRecord } from "../types/api";

interface PaymentSearchPageProps {
  demoMode: boolean;
  isActive?: boolean;
}

const STATUS_FILTERS: { label: string; value: BusinessStatus | null }[] = [
  { label: "All",                         value: null },
  { label: "With Bank",                   value: "WITH BANK" },
  { label: "Sent to Scheme",              value: "SENT TO SCHEME" },
  { label: "With Beneficiary Bank",       value: "WITH BENEFICIARY BANK" },
  { label: "Rejected by Scheme",          value: "REJECTED BY SCHEME" },
  { label: "Rejected by Beneficiary Bank",value: "REJECTED BY BENEFICIARY BANK" },
];

export function PaymentSearchPage({ demoMode, isActive }: PaymentSearchPageProps) {
  const [query, setQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<BusinessStatus | null>(null);
  const [batchFilter, setBatchFilter] = useState<string>("all");
  const [results, setResults] = useState<PaymentRecord[]>([]);
  const [selected, setSelected] = useState<PaymentRecord | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Re-fetch silently when the page becomes visible again after keep-alive navigation.
  const mountedOnce = useRef(false);
  const prevActive = useRef(false);
  useEffect(() => {
    if (!mountedOnce.current) {
      mountedOnce.current = true;
      prevActive.current = isActive === true;
      return;
    }
    if (isActive && !prevActive.current) {
      setRefreshKey((k) => k + 1);
    }
    prevActive.current = isActive === true;
  }, [isActive]);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);
    const call = demoMode
      ? api.searchPayments(query)
      : api.searchPaymentsLive(query);
    call
      .then((r) => {
        if (!mounted) return;
        setResults(r);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load payments from backend.");
        setLoading(false);
      });
    return () => {
      mounted = false;
    };
  // refreshKey is intentionally included so revisiting the page triggers a re-fetch.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, demoMode, refreshKey]);

  const distinctBatchIds = Array.from(new Set(results.map((p) => p.batchId))).sort();

  const filtered = results.filter((p) => {
    if (statusFilter && p.currentStatus !== statusFilter) return false;
    if (batchFilter !== "all" && p.batchId !== batchFilter) return false;
    return true;
  });

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <div className="page__eyebrow">Find</div>
          <h1 className="page__title">Payment Search</h1>
          <p className="page__subtitle">
            {demoMode
              ? "Demo Mode ON — find payments from the scripted SME-aligned mock records."
              : "Live Folder Mode — no mock data is shown. Upload a CCD file via the Demo Simulator to populate this view."}
          </p>
        </div>
      </header>

      {/* Search box is always visible regardless of demoMode */}
      <section className="card">
        <label className="field">
          <span className="field__label">Search</span>
          <input
            className="field__control field__control--lg"
            placeholder="Trace number, payment ID, customer, batch, beneficiary…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
        </label>

        <div className="filter-chips">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.label}
              type="button"
              className={`filter-chip${statusFilter === f.value ? " filter-chip--active" : ""}`}
              onClick={() => setStatusFilter(f.value)}
            >
              {f.label}
              {f.value !== null && (
                <span className="filter-chip__count">
                  {results.filter((p) => p.currentStatus === f.value).length}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="filter-row filter-row--batch">
          <label className="filter-row__label" htmlFor="batch-filter">Batch</label>
          <select
            id="batch-filter"
            className="field__control filter-row__select"
            value={batchFilter}
            onChange={(e) => setBatchFilter(e.target.value)}
          >
            <option value="all">All batches ({results.length} payment{results.length === 1 ? "" : "s"})</option>
            {distinctBatchIds.map((bid) => (
              <option key={bid} value={bid}>
                {bid} — {results.filter((p) => p.batchId === bid).length} payment{results.filter((p) => p.batchId === bid).length === 1 ? "" : "s"}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-row__count">
          {loading ? "Searching…" : `${filtered.length} result${filtered.length === 1 ? "" : "s"}`}
        </div>
        {error && <div className="card__error">Backend error: {error}</div>}
      </section>

      <section className="card">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Trace</th>
                <th>Customer</th>
                <th>Beneficiary</th>
                <th>Batch</th>
                <th className="table__num">Amount</th>
                <th>Status</th>
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
                  </td>
                  <td>{p.beneficiaryName}</td>
                  <td>
                    <div>{p.batchId}</div>
                    <div className="table__sub">{p.cycleTime}</div>
                  </td>
                  <td className="table__num">${p.amount.toFixed(2)}</td>
                  <td>
                    <StatusBadge status={p.currentStatus} size="sm" />
                  </td>
                  <td className="table__action">
                    <button
                      type="button"
                      className="button button--link"
                      onClick={() => setSelected(p)}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="table__empty">
                    No payments match your search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <PaymentDetailDrawer payment={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
