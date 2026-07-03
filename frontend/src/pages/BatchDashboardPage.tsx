import { useState } from "react";
import { BatchDashboard } from "../components/BatchDashboard";
import { LiveBatchDashboard } from "../components/LiveBatchDashboard";
import { PaymentDetailDrawer } from "../components/PaymentDetailDrawer";
import type { PaymentRecord } from "../types/api";

interface BatchDashboardPageProps {
  demoMode: boolean;
}

export function BatchDashboardPage({ demoMode }: BatchDashboardPageProps) {
  const [selected, setSelected] = useState<PaymentRecord | null>(null);

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <div className="page__eyebrow">Operations</div>
          <h1 className="page__title">Batch Dashboard</h1>
          <p className="page__subtitle">
            {demoMode
              ? "Demo Mode ON: predefined SME-aligned mock data grouped by batch and cycle."
              : "Demo Mode OFF: live backend ledger from parsed CCD and file evidence."}
          </p>
        </div>
      </header>

      {demoMode ? (
        <>
          <BatchDashboard onSelectPayment={setSelected} />
          <PaymentDetailDrawer
            payment={selected}
            onClose={() => setSelected(null)}
          />
        </>
      ) : (
        <LiveBatchDashboard />
      )}
    </div>
  );
}
