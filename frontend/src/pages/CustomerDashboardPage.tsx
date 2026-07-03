import { useState } from "react";
import { CustomerDashboard } from "../components/CustomerDashboard";
import { PaymentDetailDrawer } from "../components/PaymentDetailDrawer";
import type { PaymentRecord } from "../types/api";

export function CustomerDashboardPage() {
  const [selected, setSelected] = useState<PaymentRecord | null>(null);

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <div className="page__eyebrow">Operations</div>
          <h1 className="page__title">Customer Dashboard</h1>
          <p className="page__subtitle">
            All payments for a customer across batches and dates, with historical
            rejection context. Demo Mode ON uses the scripted SME-aligned story.
          </p>
        </div>
      </header>

      <CustomerDashboard onSelectPayment={setSelected} />
      <PaymentDetailDrawer payment={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
