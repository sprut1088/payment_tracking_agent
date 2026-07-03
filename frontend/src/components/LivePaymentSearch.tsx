import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchLiveLedger,
  formatDollars,
  formatTimestamp,
  latestEvidenceSummary,
} from "../api/ledger";
import type { LedgerPayment, PaymentLedgerView } from "../types/api";
import { StatusBadge } from "./StatusBadge";

const EMPTY_STATE_MESSAGE =
  "No live ledger payments yet. Go to Demo Simulator, seed CCD files, then click Scan CCD.";

function matchesQuery(payment: LedgerPayment, needle: string): boolean {
  if (!needle) return true;
  const q = needle.toLowerCase();
  return (
    payment.payment_id.toLowerCase().includes(q) ||
    payment.trace_number.toLowerCase().includes(q) ||
    payment.individual_id_number.toLowerCase().includes(q) ||
    payment.individual_name.toLowerCase().includes(q) ||
    payment.batch_key.toLowerCase().includes(q)
  );
}

interface LiveDetailProps {
  payment: LedgerPayment;
  onClose: () => void;
}

function LivePaymentDetail({ payment, onClose }: LiveDetailProps) {
  return (
    <section className="card live-detail">
      <header className="card__header card__header--split live-detail__header">
        <div>
          <div className="page__eyebrow">Live payment detail</div>
          <h3 className="card__title">{payment.payment_id}</h3>
          <p className="card__subtitle">
            Trace <span className="table__mono">{payment.trace_number}</span> ·
            Batch <span className="table__mono">{payment.batch_key}</span>
          </p>
        </div>
        <button type="button" className="button button--ghost" onClick={onClose}>
          Close
        </button>
      </header>

      <div className="live-detail__grid">
        <div className="live-detail__field">
          <span className="live-detail__label">Current status</span>
          <StatusBadge status={payment.current_status} />
        </div>
        <div className="live-detail__field">
          <span className="live-detail__label">Amount</span>
          <div className="live-detail__amount">
            {formatDollars(payment.amount_cents)}
          </div>
        </div>
        <div className="live-detail__field">
          <span className="live-detail__label">Individual</span>
          <div>{payment.individual_name}</div>
          <div className="live-detail__sub">{payment.individual_id_number}</div>
        </div>
        <div className="live-detail__field">
          <span className="live-detail__label">Receiving DFI</span>
          <div className="table__mono">
            {payment.receiving_dfi_identification}
          </div>
          <div className="live-detail__sub">
            Acct {payment.masked_account_number}
          </div>
        </div>
        <div className="live-detail__field">
          <span className="live-detail__label">Source file</span>
          <div className="table__mono">{payment.source_file}</div>
        </div>
        <div className="live-detail__field">
          <span className="live-detail__label">Batch key</span>
          <div className="table__mono">{payment.batch_key}</div>
        </div>
      </div>

      <section className="live-detail__section">
        <h4 className="live-detail__section-title">Status history</h4>
        {payment.status_history.length === 0 ? (
          <p className="live-detail__empty">No status history yet.</p>
        ) : (
          <ol className="mini-timeline">
            {payment.status_history.map((h, idx) => (
              <li key={idx} className="mini-timeline__item">
                <div className="mini-timeline__time">
                  {formatTimestamp(h.at)}
                </div>
                <div className="mini-timeline__body">
                  <StatusBadge status={h.status} size="sm" />
                  <div className="mini-timeline__reason">
                    {h.evidence.summary}
                  </div>
                  <div className="mini-timeline__source">
                    {h.evidence.source}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="live-detail__section">
        <h4 className="live-detail__section-title">Evidence</h4>
        {payment.evidence.length === 0 ? (
          <p className="live-detail__empty">No evidence attached yet.</p>
        ) : (
          <ul className="live-detail__evidence-list">
            {payment.evidence.map((ev, idx) => (
              <li key={idx} className="live-detail__evidence-item">
                <div className="live-detail__evidence-head">
                  <span className="live-detail__evidence-source">
                    {ev.source}
                  </span>
                  <span className="live-detail__evidence-time">
                    {formatTimestamp(ev.recorded_at)}
                  </span>
                </div>
                <div className="live-detail__evidence-summary">
                  {ev.summary}
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="live-detail__caveat">
          Settlement summary evidence is aggregate only. No payment-level
          clearing is claimed from settlement summary.
        </p>
      </section>
    </section>
  );
}

export function LivePaymentSearch() {
  const [ledger, setLedger] = useState<PaymentLedgerView | null>(null);
  const [query, setQuery] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

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
  const results = useMemo(
    () => payments.filter((p) => matchesQuery(p, query.trim())),
    [payments, query],
  );

  const selected = useMemo(
    () => results.find((p) => p.payment_id === selectedId) ?? null,
    [results, selectedId],
  );

  return (
    <>
      <section className="card">
        <header className="card__header card__header--split">
          <div>
            <p className="live-ledger__mode-label">
              Live backend ledger from parsed CCD and file evidence
            </p>
            <p className="card__subtitle">
              Search live ledger payments by payment ID, trace number,
              individual ID, individual name, or batch key.
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

        <label className="field">
          <span className="field__label">Search</span>
          <input
            className="field__control field__control--lg"
            placeholder="Payment ID, trace number, individual ID, individual name, batch key…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
        </label>
        <div className="filter-row__count">
          {isRefreshing
            ? "Refreshing…"
            : `${results.length} result${results.length === 1 ? "" : "s"} of ${payments.length}`}
        </div>

        {error && <div className="local-flow__error">{error}</div>}
      </section>

      <section className="card">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Payment ID</th>
                <th>Trace number</th>
                <th>Individual name</th>
                <th>Individual ID</th>
                <th>Batch key</th>
                <th className="table__num">Amount</th>
                <th>Status</th>
                <th>Latest evidence</th>
                <th className="table__action">Detail</th>
              </tr>
            </thead>
            <tbody>
              {payments.length === 0 && (
                <tr>
                  <td colSpan={9} className="table__empty">
                    {EMPTY_STATE_MESSAGE}
                  </td>
                </tr>
              )}
              {payments.length > 0 && results.length === 0 && (
                <tr>
                  <td colSpan={9} className="table__empty">
                    No payments match your search.
                  </td>
                </tr>
              )}
              {results.map((payment) => (
                <tr key={payment.payment_id}>
                  <td className="table__mono">{payment.payment_id}</td>
                  <td className="table__mono">{payment.trace_number}</td>
                  <td>{payment.individual_name}</td>
                  <td className="table__mono">
                    {payment.individual_id_number}
                  </td>
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
                  <td className="table__action">
                    <button
                      type="button"
                      className="button button--link"
                      onClick={() => setSelectedId(payment.payment_id)}
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

      {selected && (
        <LivePaymentDetail
          payment={selected}
          onClose={() => setSelectedId(null)}
        />
      )}
    </>
  );
}
