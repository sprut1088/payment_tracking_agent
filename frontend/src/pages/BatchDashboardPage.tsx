import { useState } from "react";
import { BatchDashboard } from "../components/BatchDashboard";
import { PaymentDetailDrawer } from "../components/PaymentDetailDrawer";
import type { PaymentRecord } from "../types/api";

export function BatchDashboardPage() {
  const [selected, setSelected] = useState<PaymentRecord | null>(null);

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <div className="page__eyebrow">Operations</div>
          <h1 className="page__title">Batch Dashboard</h1>
          <p className="page__subtitle">
            Payments grouped by batch and cycle. Click a payment to inspect
            evidence and its status timeline.
          </p>
        </div>
      </header>

      <BatchDashboard onSelectPayment={setSelected} />
      <PaymentDetailDrawer payment={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
