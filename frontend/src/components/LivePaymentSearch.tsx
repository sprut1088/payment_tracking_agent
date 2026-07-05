import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import {
  fetchLiveLedger,
  formatDollars,
  formatTimestamp,
  latestEvidenceSummary,
} from "../api/ledger";
import type {
  AIExplanationResponse,
  BatchRiskClassification,
  CustomerRiskClassification,
  ExplanationPreset,
  LedgerPayment,
  PaymentLedgerView,
  RiskClassification,
  RiskClassificationTrigger,
} from "../types/api";
import { StatusBadge } from "./StatusBadge";

const EMPTY_STATE_MESSAGE =
  "No live ledger payments yet. Go to Demo Simulator, switch Demo Mode OFF, seed CCD files, then click Scan CCD.";

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

function confidencePercentFromBand(
  band: "LOW" | "MEDIUM" | "HIGH",
): number {
  if (band === "HIGH") return 85;
  if (band === "MEDIUM") return 65;
  return 35;
}

function paymentRiskRowClass(payment: LedgerPayment): string {
  const band = payment.current_risk_classification?.risk_band.toLowerCase();
  if (!band) return "";
  return `table__row-risk--${band}`;
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

      <AiExplanationPanel key={payment.payment_id} payment={payment} />
      <RiskClassificationView
        key={`risk-${payment.payment_id}`}
        payment={payment}
      />
    </section>
  );
}

interface AiExplanationPanelProps {
  payment: LedgerPayment;
}

function AiExplanationPanel({ payment }: AiExplanationPanelProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<AIExplanationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preset, setPreset] = useState<ExplanationPreset>("operations");

  const onGenerate = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.generateAiExplanation(payment.payment_id, preset);
      setResult(response);
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to generate AI explanation.";
      setError(message);
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  }, [payment.payment_id, preset]);

  const presetOptions: { value: ExplanationPreset; label: string }[] = [
    { value: "operations", label: "Operations" },
    { value: "customer_safe", label: "Customer-safe" },
    { value: "executive", label: "Executive" },
  ];

  return (
    <section className="live-detail__section ai-panel">
      <div className="ai-panel__header">
        <h4 className="live-detail__section-title">AI explanation</h4>
        <p className="ai-panel__subtitle">
          Claude explains the deterministic evidence on demand. Claude does
          not determine payment status.
        </p>
        <p className="ai-panel__helper">
          Claude explains deterministic ledger evidence. It does not determine
          payment status.
        </p>
      </div>
      <div
        className="ai-panel__presets"
        role="radiogroup"
        aria-label="Explanation style"
      >
        {presetOptions.map((opt) => {
          const active = preset === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={active}
              className={
                "ai-panel__preset-button" +
                (active ? " ai-panel__preset-button--active" : "")
              }
              onClick={() => setPreset(opt.value)}
              disabled={isLoading}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      <div className="ai-panel__controls">
        <button
          type="button"
          className="button"
          onClick={onGenerate}
          disabled={isLoading}
        >
          {isLoading ? "Generating Claude explanation..." : "Generate AI explanation"}
        </button>
        {result && (
          <span className="ai-panel__meta">
            Provider {result.provider} · Model{" "}
            <span className="table__mono">{result.model}</span> · Generated{" "}
            {formatTimestamp(result.generated_at)}
          </span>
        )}
      </div>

      {error && (
        <p className="ai-panel__error" role="alert">
          {error}
        </p>
      )}

      {result && !error && (
        <div className="ai-panel__result">
          <div className="ai-panel__field">
            <span className="ai-panel__label">Summary</span>
            <p>{result.summary || "(No summary returned.)"}</p>
          </div>
          <div className="ai-panel__field">
            <span className="ai-panel__label">Status explanation</span>
            <p>{result.status_explanation || "(No status explanation returned.)"}</p>
          </div>
          <div className="ai-panel__field">
            <span className="ai-panel__label">Evidence used</span>
            {result.evidence_used.length === 0 ? (
              <p className="live-detail__empty">
                Claude did not list any evidence items.
              </p>
            ) : (
              <ul className="ai-panel__list">
                {result.evidence_used.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            )}
          </div>
          <div className="ai-panel__field">
            <span className="ai-panel__label">Limitations</span>
            {result.limitations.length === 0 ? (
              <p className="live-detail__empty">
                Claude did not list any limitations.
              </p>
            ) : (
              <ul className="ai-panel__list">
                {result.limitations.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            )}
          </div>
          <div className="ai-panel__field">
            <span className="ai-panel__label">Recommended action</span>
            <p>{result.recommended_action || "(No recommended action returned.)"}</p>
          </div>
          <div className="ai-panel__field">
            <span className="ai-panel__label">Customer-safe message</span>
            <p>{result.customer_safe_message || "(No customer message returned.)"}</p>
          </div>
        </div>
      )}
    </section>
  );
}

interface RiskClassificationViewProps {
  payment: LedgerPayment;
}

const TRIGGER_LABEL: Record<RiskClassificationTrigger, string> = {
  CCD_UPLOAD: "CCD upload",
  SETTLEMENT_OR_SCHEME_REJECT: "Settlement / scheme reject",
  NACHA_RETURN: "NACHA return",
};

function RiskClassificationCard({
  classification,
  variant,
}: {
  classification: RiskClassification;
  variant: "current" | "history";
}) {
  const band = classification.risk_band.toLowerCase();
  const confidence = classification.clearing_confidence.toLowerCase();
  return (
    <div
      className={
        "ai-panel__result ai-risk-card" +
        (variant === "history" ? " ai-risk-card--history" : "")
      }
    >
      <div className="ai-panel__risk-badges">
        <span className={`ai-risk-badge ai-risk-badge--${band}`}>
          Risk band: {classification.risk_band}
        </span>
        <span className="ai-risk-badge ai-risk-badge--score">
          Score: {classification.risk_score}/100
        </span>
        <span
          className={`ai-risk-badge ai-risk-badge--confidence ai-risk-badge--${confidence}`}
        >
          Clearing confidence: {classification.clearing_confidence}
        </span>
      </div>
      <p className="ai-panel__helper">
        {classification.clearing_confidence_note}
      </p>
      <div className="ai-panel__field">
        <span className="ai-panel__label">Trigger</span>
        <p>
          {TRIGGER_LABEL[classification.trigger]}{" "}
          <span className="live-detail__evidence-time">
            · Classified {formatTimestamp(classification.classified_at)}
          </span>
        </p>
      </div>
      <div className="ai-panel__field">
        <span className="ai-panel__label">Summary</span>
        <p>{classification.summary}</p>
      </div>
      <div className="ai-panel__field">
        <span className="ai-panel__label">Risk drivers</span>
        {classification.risk_drivers.length === 0 ? (
          <p className="live-detail__empty">No risk drivers recorded.</p>
        ) : (
          <ul className="ai-panel__list">
            {classification.risk_drivers.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        )}
      </div>
      <div className="ai-panel__field">
        <span className="ai-panel__label">Evidence used</span>
        {classification.evidence_used.length === 0 ? (
          <p className="live-detail__empty">No evidence items listed.</p>
        ) : (
          <ul className="ai-panel__list">
            {classification.evidence_used.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        )}
      </div>
      <div className="ai-panel__field">
        <span className="ai-panel__label">Recommendation</span>
        <p>{classification.recommendation || "(No recommendation recorded.)"}</p>
      </div>
      {classification.prior_prediction && (
        <div className="ai-panel__field">
          <span className="ai-panel__label">Prior prediction vs actual outcome</span>
          <p>{classification.prior_prediction.narrative}</p>
          <p className="ai-panel__meta">
            Prior score {classification.prior_prediction.prior_risk_score ?? "N/A"} ·
            Prior band {classification.prior_prediction.prior_risk_band ?? "N/A"} ·
            Prior clearing confidence {classification.prior_prediction.prior_clearing_confidence ?? "N/A"} ·
            Outcome {classification.prior_prediction.actual_outcome_status} ·
            Alignment {classification.prior_prediction.outcome_alignment}
          </p>
        </div>
      )}
      <p className="ai-panel__meta">
        Provider {classification.provider} · Model{" "}
        <span className="table__mono">{classification.model}</span>
      </p>
    </div>
  );
}

function RiskClassificationView({ payment }: RiskClassificationViewProps) {
  const current = payment.current_risk_classification;
  const history = payment.risk_classification_history;

  return (
    <section className="live-detail__section ai-panel ai-risk-panel">
      <div className="ai-panel__header">
        <h4 className="live-detail__section-title">AI Payment Risk Classification</h4>
        <p className="ai-panel__helper">
          AI risk classification uses deterministic ledger evidence, demo
          customer history, and available CCD validation findings. It does not
          determine payment status, credit risk, or fraud risk.
        </p>
        <p className="ai-panel__helper">
          Clearing confidence is an operational AI confidence score, not
          payment-level clearing evidence.
        </p>
      </div>
      {current === null ? (
        <p className="live-detail__empty">
          No AI risk classification stamped yet for this payment.
        </p>
      ) : (
        <RiskClassificationCard classification={current} variant="current" />
      )}
      {history.length > 0 && (
        <div className="ai-risk-history">
          <h5 className="live-detail__section-title live-detail__section-title--sub">
            Prior classifications
          </h5>
          <ol className="ai-risk-history__list">
            {[...history].reverse().map((entry, idx) => (
              <li key={idx}>
                <RiskClassificationCard
                  classification={entry}
                  variant="history"
                />
              </li>
            ))}
          </ol>
        </div>
      )}
      <CustomerRiskView
        current={payment.current_customer_risk_classification}
        history={payment.customer_risk_classification_history}
      />
      <BatchRiskView
        current={payment.current_batch_risk_classification}
        history={payment.batch_risk_classification_history}
      />
    </section>
  );
}

function CustomerRiskView({
  current,
  history,
}: {
  current: CustomerRiskClassification | null;
  history: CustomerRiskClassification[];
}) {
  return (
    <div className="ai-risk-related">
      <h5 className="live-detail__section-title live-detail__section-title--sub">
        Customer Risk Classification
      </h5>
      {!current ? (
        <p className="live-detail__empty">No customer risk classification stamped.</p>
      ) : (
        <div className="ai-panel__result ai-risk-card ai-risk-card--history">
          <div className="ai-panel__risk-badges">
            <span className={`ai-risk-badge ai-risk-badge--${current.risk_band.toLowerCase()}`}>
              Customer Risk Band: {current.risk_band}
            </span>
            <span className="ai-risk-badge ai-risk-badge--score">
              Risk Score: {current.risk_score}
            </span>
          </div>
          <p>{current.summary}</p>
          <p className="ai-panel__meta">Recent rejection counts from evidence:</p>
          <ul className="ai-panel__list">
            {current.evidence_used.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
          <p className="ai-panel__meta">{current.recommendation}</p>
        </div>
      )}
      {history.length > 0 && (
        <p className="ai-panel__meta">History entries: {history.length}</p>
      )}
    </div>
  );
}

function BatchRiskView({
  current,
  history,
}: {
  current: BatchRiskClassification | null;
  history: BatchRiskClassification[];
}) {
  return (
    <div className="ai-risk-related">
      <h5 className="live-detail__section-title live-detail__section-title--sub">
        Batch Risk Classification
      </h5>
      {!current ? (
        <p className="live-detail__empty">No batch risk classification stamped.</p>
      ) : (
        <div className="ai-panel__result ai-risk-card ai-risk-card--history">
          <div className="ai-panel__risk-badges">
            <span className={`ai-risk-badge ai-risk-badge--${current.risk_band.toLowerCase()}`}>
              Batch Risk Band: {current.risk_band}
            </span>
            <span className="ai-risk-badge ai-risk-badge--score">
              Risk Score: {current.risk_score}
            </span>
          </div>
          <p>{current.summary}</p>
          <p className="ai-panel__meta">Validation findings</p>
          {current.validation_findings.length === 0 ? (
            <p className="live-detail__empty">No validation findings listed.</p>
          ) : (
            <ul className="ai-panel__list">
              {current.validation_findings.map((item, idx) => (
                <li key={idx}>{item}</li>
              ))}
            </ul>
          )}
          <p className="ai-panel__meta">{current.recommendation}</p>
        </div>
      )}
      {history.length > 0 && (
        <p className="ai-panel__meta">History entries: {history.length}</p>
      )}
    </div>
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
            <p className="table__note">
              AI risk classification uses deterministic ledger evidence, demo
              customer history, and available CCD validation findings. It does
              not determine payment status, credit risk, or fraud risk.
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
                <th>Risk</th>
                <th className="table__num">Amount</th>
                <th>Status</th>
                <th>Latest evidence</th>
                <th className="table__action">Detail</th>
              </tr>
            </thead>
            <tbody>
              {payments.length === 0 && (
                <tr>
                  <td colSpan={10} className="table__empty">
                    {EMPTY_STATE_MESSAGE}
                  </td>
                </tr>
              )}
              {payments.length > 0 && results.length === 0 && (
                <tr>
                  <td colSpan={10} className="table__empty">
                    No payments match your search.
                  </td>
                </tr>
              )}
              {results.map((payment) => (
                <tr
                  key={payment.payment_id}
                  className={paymentRiskRowClass(payment)}
                >
                  <td className="table__mono">{payment.payment_id}</td>
                  <td className="table__mono">{payment.trace_number}</td>
                  <td>{payment.individual_name}</td>
                  <td className="table__mono">
                    {payment.individual_id_number}
                  </td>
                  <td className="table__mono">{payment.batch_key}</td>
                  <td>
                    {payment.current_risk_classification ? (
                      <div className="risk-cell">
                        <span
                          className={
                            "ai-risk-badge ai-risk-badge--" +
                            payment.current_risk_classification.risk_band.toLowerCase()
                          }
                        >
                          {payment.current_risk_classification.risk_band}
                        </span>
                        <div className="risk-cell__meta">
                          {payment.current_risk_classification.risk_score}/100
                        </div>
                        <div className="risk-cell__meta">
                          Confidence {payment.current_risk_classification.clearing_confidence} · {confidencePercentFromBand(payment.current_risk_classification.clearing_confidence)}%
                        </div>
                      </div>
                    ) : (
                      <span className="table__subtle">N/A</span>
                    )}
                  </td>
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
        <p className="table__note">
          Clearing confidence is an operational AI confidence score, not
          payment-level clearing evidence.
        </p>
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
