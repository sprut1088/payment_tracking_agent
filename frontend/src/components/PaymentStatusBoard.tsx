import type { SimulationState } from "../types/api";
import { StatusBadge } from "./StatusBadge";

interface PaymentStatusBoardProps {
  state: SimulationState;
}

export function PaymentStatusBoard({ state }: PaymentStatusBoardProps) {
  const { summary } = state;
  const items: Array<{ status: Parameters<typeof StatusBadge>[0]["status"]; count: number }> = [
    { status: "WITH BANK", count: summary.withBank },
    { status: "SENT TO SCHEME", count: summary.sentToScheme },
    { status: "WITH BENEFICIARY BANK", count: summary.withBeneficiaryBank },
    { status: "REJECTED BY SCHEME", count: summary.rejectedByScheme },
    {
      status: "REJECTED BY BENEFICIARY BANK",
      count: summary.rejectedByBeneficiaryBank,
    },
  ];

  return (
    <section className="card">
      <header className="card__header">
        <h2 className="card__title">Payment status board</h2>
        <p className="card__subtitle">
          Live counts across all batches in this scenario. Totals:{" "}
          <strong>{summary.totalPayments}</strong> payments tracked. No
          payment-level clearing is inferred from settlement summary evidence.
        </p>
      </header>
      <div className="status-board">
        {items.map((i) => (
          <div key={i.status} className="status-board__cell">
            <div className="status-board__count">{i.count}</div>
            <StatusBadge status={i.status} size="sm" />
          </div>
        ))}
      </div>
    </section>
  );
}
