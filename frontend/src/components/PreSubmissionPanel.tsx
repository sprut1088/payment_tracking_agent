/**
 * PreSubmissionPanel — shows the AI-driven pre-submission risk validation
 * result for a CCD batch BEFORE payments are sent to the ACH scheme.
 *
 * Displays:
 *  - Batch-level risk badge + AI narrative summary
 *  - HOLD / REVIEW / PROCEED count tiles
 *  - Release / Reject action buttons when batch is fully HELD
 *  - Per-customer risk table with action recommendation
 *  - Expandable per-payment trace list per customer
 */
import { useState } from "react";
import { api } from "../api/client";
import type {
  BatchPreSubmissionResult,
  PreSubmissionCustomerSummary,
  PreSubmissionAction,
} from "../types/api";

interface PreSubmissionPanelProps {
  result: BatchPreSubmissionResult;
  uploadId: string;
  holdCount: number;        // WITH_BANK count from BatchSummary — > 0 means batch is held
  onAction?: () => void;    // refresh callback after release / reject
}

interface PreSubmissionPanelProps {
  result: BatchPreSubmissionResult;
}

function actionBadgeClass(action: PreSubmissionAction): string {
  switch (action) {
    case "HOLD":   return "pre-sub__action-badge pre-sub__action-badge--hold";
    case "REVIEW": return "pre-sub__action-badge pre-sub__action-badge--review";
    default:       return "pre-sub__action-badge pre-sub__action-badge--proceed";
  }
}

function riskBadgeClass(level: string): string {
  return `risk risk--${level.toLowerCase()}`;
}

function CustomerRow({ c }: { c: PreSubmissionCustomerSummary }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr className={`pre-sub__row pre-sub__row--${c.action.toLowerCase()}`}>
        <td>
          <button
            type="button"
            className="button button--link pre-sub__expand"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
          >
            {open ? "▾" : "▸"}
          </button>
          {c.customer_name}
          <span className="pre-sub__customer-id">{c.customer_id}</span>
        </td>
        <td className="table__num">{c.payment_count}</td>
        <td className="table__num">${c.total_amount.toFixed(2)}</td>
        <td>
          <span className={riskBadgeClass(c.risk_level)}>{c.risk_level}</span>
        </td>
        <td>
          <span className={actionBadgeClass(c.action)}>{c.action}</span>
        </td>
        <td className="pre-sub__rec">{c.ai_recommendation}</td>
      </tr>
      {open && (
        <tr className="pre-sub__detail-row">
          <td colSpan={6}>
            <div className="pre-sub__risk-reason">{c.risk_reason}</div>
            <div className="pre-sub__traces">
              <span className="pre-sub__traces-label">Trace numbers:</span>
              {c.trace_numbers.map((t) => (
                <code key={t} className="pre-sub__trace">{t}</code>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function PreSubmissionPanel({ result, uploadId, holdCount, onAction }: PreSubmissionPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);

  const batchIsHeld = holdCount > 0 && result.hold_count > 0;

  const handleRelease = async () => {
    setBusy(true); setActionMsg(null); setActionErr(null);
    try {
      const r = await api.releaseHold(uploadId);
      setActionMsg(`Released — ${r.released} payment(s) advanced to Sent to Scheme.`);
      onAction?.();
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "Release failed.");
    } finally { setBusy(false); }
  };

  const handleReject = async () => {
    if (!confirm("Permanently reject this batch? Payments will be marked Rejected by Scheme.")) return;
    setBusy(true); setActionMsg(null); setActionErr(null);
    try {
      const r = await api.rejectHold(uploadId);
      setActionMsg(`Rejected — ${r.rejected} payment(s) marked Rejected by Scheme.`);
      onAction?.();
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "Reject failed.");
    } finally { setBusy(false); }
  };

  const validatedTime = new Date(result.validated_at).toLocaleTimeString("en-GB", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });

  return (
    <div className="pre-sub">
      <button
        type="button"
        className="pre-sub__header"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <div className="pre-sub__header-left">
          <span className="pre-sub__toggle">{expanded ? "▾" : "▸"}</span>
          <span className="pre-sub__title">Pre-Submission Risk Validation</span>
          <span className={riskBadgeClass(result.batch_risk_level)}>
            {result.batch_risk_level} batch risk
          </span>
          {result.hold_count > 0 && (
            <span className="pre-sub__action-badge pre-sub__action-badge--hold">
              {result.hold_count} Hold
            </span>
          )}
          {result.review_count > 0 && (
            <span className="pre-sub__action-badge pre-sub__action-badge--review">
              {result.review_count} Review
            </span>
          )}
        </div>
        <div className="pre-sub__header-right">
          <span className="pre-sub__time">Validated at {validatedTime}</span>
          <span className="pre-sub__collapse-btn" aria-hidden>
            {expanded ? "▲" : "▼"}
          </span>
        </div>
      </button>

      {(actionMsg || actionErr) && (
        <div className={actionMsg ? "pre-sub__action-notice pre-sub__action-notice--ok" : "pre-sub__action-notice pre-sub__action-notice--err"}>
          {actionMsg ?? actionErr}
        </div>
      )}

      {batchIsHeld && !actionMsg && (
        <div className="pre-sub__hold-bar">
          <span className="pre-sub__hold-label">
            ⚠ Batch is HELD — {result.hold_count} payment(s) flagged by pre-submission validation.
            Operator action required before scheme submission.
          </span>
          <div className="pre-sub__hold-actions">
            <button
              type="button"
              className="button button--sm button--primary"
              disabled={busy}
              onClick={() => void handleRelease()}
            >
              Release to Scheme
            </button>
            <button
              type="button"
              className="button button--sm button--danger"
              disabled={busy}
              onClick={() => void handleReject()}
            >
              Reject Batch
            </button>
          </div>
        </div>
      )}

      {expanded && (
        <>
          <p className="pre-sub__summary">{result.ai_batch_summary}</p>

          <div className="pre-sub__counts">
            <div className="pre-sub__count pre-sub__count--hold">
              <div className="pre-sub__count-value">{result.hold_count}</div>
              <div className="pre-sub__count-label">Hold</div>
            </div>
            <div className="pre-sub__count pre-sub__count--review">
              <div className="pre-sub__count-value">{result.review_count}</div>
              <div className="pre-sub__count-label">Review</div>
            </div>
            <div className="pre-sub__count pre-sub__count--proceed">
              <div className="pre-sub__count-value">{result.proceed_count}</div>
              <div className="pre-sub__count-label">Proceed</div>
            </div>
            <div className="pre-sub__count pre-sub__count--high">
              <div className="pre-sub__count-value">{result.high_risk_count}</div>
              <div className="pre-sub__count-label">High Risk</div>
            </div>
            <div className="pre-sub__count pre-sub__count--medium">
              <div className="pre-sub__count-value">{result.medium_risk_count}</div>
              <div className="pre-sub__count-label">Medium Risk</div>
            </div>
            <div className="pre-sub__count pre-sub__count--low">
              <div className="pre-sub__count-value">{result.low_risk_count}</div>
              <div className="pre-sub__count-label">Low Risk</div>
            </div>
          </div>

          {result.customer_summaries.length > 0 && (
            <div className="table-wrap pre-sub__table-wrap">
              <table className="table pre-sub__table">
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th className="table__num">Payments</th>
                    <th className="table__num">Amount</th>
                    <th>Risk</th>
                    <th>Action</th>
                    <th>AI Recommendation</th>
                  </tr>
                </thead>
                <tbody>
                  {result.customer_summaries
                    .slice()
                    .sort((a, b) => {
                      const actionOrder: Record<string, number> = { HOLD: 0, REVIEW: 1, PROCEED: 2 };
                      const riskOrder: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };
                      return (
                        (actionOrder[a.action] ?? 9) - (actionOrder[b.action] ?? 9) ||
                        (riskOrder[a.risk_level] ?? 9) - (riskOrder[b.risk_level] ?? 9)
                      );
                    })
                    .map((c) => (
                      <CustomerRow key={c.customer_id} c={c} />
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
