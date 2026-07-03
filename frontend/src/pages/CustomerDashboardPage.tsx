import { useState } from "react";
import { CustomerDashboard } from "../components/CustomerDashboard";
import { LiveCustomerDashboard } from "../components/LiveCustomerDashboard";
import { PaymentDetailDrawer } from "../components/PaymentDetailDrawer";
import type { PaymentRecord } from "../types/api";

interface CustomerDashboardPageProps {
  demoMode: boolean;
}

export function CustomerDashboardPage({ demoMode }: CustomerDashboardPageProps) {
  const [selected, setSelected] = useState<PaymentRecord | null>(null);

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <div className="page__eyebrow">Operations</div>
          <h1 className="page__title">Customer Dashboard</h1>
          <p className="page__subtitle">
            {demoMode
              ? "Demo Mode ON: scripted SME-aligned mock story with historical rejection context."
              : "Demo Mode OFF: live backend ledger grouped by individual ID and name."}
          </p>
        </div>
      </header>

      {demoMode ? (
        <>
          <CustomerDashboard onSelectPayment={setSelected} />
          <PaymentDetailDrawer
            payment={selected}
            onClose={() => setSelected(null)}
          />
        </>
      ) : (
        <LiveCustomerDashboard />
      )}
    </div>
  );
}
