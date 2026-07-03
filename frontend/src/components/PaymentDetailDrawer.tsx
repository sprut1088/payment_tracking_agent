import type { PaymentRecord } from "../types/api";
import { EvidenceViewer } from "./EvidenceViewer";
import { StatusBadge } from "./StatusBadge";

interface PaymentDetailDrawerProps {
  payment: PaymentRecord | null;
  onClose: () => void;
}

export function PaymentDetailDrawer({ payment, onClose }: PaymentDetailDrawerProps) {
  if (!payment) return null;

  return (
    <div className="drawer" role="dialog" aria-modal="true">
      <div className="drawer__scrim" onClick={onClose} />
      <aside className="drawer__panel">
        <header className="drawer__header">
          <div>
            <div className="drawer__eyebrow">Payment detail</div>
            <h2 className="drawer__title">{payment.paymentId}</h2>
            <div className="drawer__subtitle">
              Trace <span className="table__mono">{payment.traceNumber}</span> · Batch{" "}
              {payment.batchId} · Cycle {payment.cycleTime}
            </div>
          </div>
          <button type="button" className="button button--ghost" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="drawer__grid">
          <div className="drawer__field">
            <span className="drawer__label">Current status</span>
            <StatusBadge status={payment.currentStatus} />
            <div className="drawer__sub">
              since {payment.statusSince} · internal {payment.internalStatus}
            </div>
          </div>
          <div className="drawer__field">
            <span className="drawer__label">Customer</span>
            <div>{payment.customerName}</div>
            <div className="drawer__sub">{payment.customerId}</div>
          </div>
          <div className="drawer__field">
            <span className="drawer__label">Beneficiary</span>
            <div>{payment.beneficiaryName}</div>
            <div className="drawer__sub">
              DFI {payment.receivingDfi} · Acct {payment.maskedAccount}
            </div>
          </div>
          <div className="drawer__field">
            <span className="drawer__label">Amount</span>
            <div className="drawer__amount">
              ${payment.amount.toFixed(2)} {payment.currency}
            </div>
          </div>
          <div className="drawer__field">
            <span className="drawer__label">Risk</span>
            <span className={`risk risk--${payment.riskLevel.toLowerCase()}`}>
              {payment.riskLevel}
            </span>
            {payment.riskReason && <div className="drawer__sub">{payment.riskReason}</div>}
          </div>
          <div className="drawer__field">
            <span className="drawer__label">Return code</span>
            <div>{payment.returnReasonCode ?? "—"}</div>
          </div>
        </div>

        <section className="drawer__section">
          <h3 className="drawer__section-title">Status timeline</h3>
          <ol className="mini-timeline">
            {payment.statusHistory.map((h, idx) => (
              <li key={idx} className="mini-timeline__item">
                <div className="mini-timeline__time">{h.timestamp}</div>
                <div className="mini-timeline__body">
                  <StatusBadge status={h.status} size="sm" />
                  <div className="mini-timeline__reason">{h.reason}</div>
                  <div className="mini-timeline__source">
                    {h.agent} · {h.source.kind}
                    {h.source.sourceFile && ` · ${h.source.sourceFile}`}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="drawer__section drawer__section--split">
          <EvidenceViewer evidence={payment.evidence} />
          <div className="explanation">
            <h3 className="drawer__section-title">Customer-safe explanation</h3>
            <p className="explanation__message">{payment.customerFriendlyMessage ?? "—"}</p>
            <div className="explanation__action">
              <span className="drawer__label">Recommended action</span>
              <div>{payment.recommendedAction ?? "—"}</div>
            </div>
            <p className="explanation__caveat">
              Explanations are deterministic and evidence-based. Settlement
              summary entries are treated as aggregate evidence and do not claim
              payment-level clearing.
            </p>
          </div>
        </section>
      </aside>
    </div>
  );
}
