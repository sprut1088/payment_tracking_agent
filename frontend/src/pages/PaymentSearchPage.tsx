import { useEffect, useState } from "react";
import { api } from "../api/client";
import { LivePaymentSearch } from "../components/LivePaymentSearch";
import { PaymentDetailDrawer } from "../components/PaymentDetailDrawer";
import { StatusBadge } from "../components/StatusBadge";
import type { PaymentRecord } from "../types/api";

interface PaymentSearchPageProps {
  demoMode: boolean;
}

export function PaymentSearchPage({ demoMode }: PaymentSearchPageProps) {
  const [query, setQuery] = useState<string>("");
  const [results, setResults] = useState<PaymentRecord[]>([]);
  const [selected, setSelected] = useState<PaymentRecord | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!demoMode) return;
    let mounted = true;
    setLoading(true);
    api.searchPayments(query).then((r) => {
      if (!mounted) return;
      setResults(r);
      setLoading(false);
    });
    return () => {
      mounted = false;
    };
  }, [query, demoMode]);

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <div className="page__eyebrow">Find</div>
          <h1 className="page__title">Payment Search</h1>
          <p className="page__subtitle">
            {demoMode
              ? "Demo Mode ON: scripted SME-aligned mock records. Search by trace, payment ID, customer, batch, or beneficiary."
              : "Demo Mode OFF: search the live backend ledger by payment ID, trace, individual ID, individual name, or batch key."}
          </p>
        </div>
      </header>

      {demoMode ? (
        <>
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
            <div className="filter-row__count">
              {loading
                ? "Searching…"
                : `${results.length} result${results.length === 1 ? "" : "s"}`}
            </div>
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
                  {results.map((p) => (
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
                  {!loading && results.length === 0 && (
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

          <PaymentDetailDrawer
            payment={selected}
            onClose={() => setSelected(null)}
          />
        </>
      ) : (
        <LivePaymentSearch />
      )}
    </div>
  );
}
