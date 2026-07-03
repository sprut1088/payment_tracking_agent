import { useEffect, useRef, useState } from "react";
import { BatchDashboard } from "../components/BatchDashboard";
import { PaymentDetailDrawer } from "../components/PaymentDetailDrawer";
import type { PaymentRecord } from "../types/api";

interface BatchDashboardPageProps {
  demoMode: boolean;
  isActive?: boolean;
}

export function BatchDashboardPage({ demoMode, isActive }: BatchDashboardPageProps) {
  const [selected, setSelected] = useState<PaymentRecord | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const mountedOnce = useRef(false);
  const prevActive = useRef(false);

  useEffect(() => {
    if (!mountedOnce.current) {
      mountedOnce.current = true;
      prevActive.current = isActive === true;
      return;
    }
    if (isActive && !prevActive.current) {
      setRefreshKey((k) => k + 1);
    }
    prevActive.current = isActive === true;
  }, [isActive]);

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <div className="page__eyebrow">Operations</div>
          <h1 className="page__title">Batch Dashboard</h1>
          <p className="page__subtitle">
            {demoMode
              ? "Demo Mode ON — showing predefined SME-aligned mock data."
              : "Live Folder Mode — no mock data is shown. Upload a CCD file via the Demo Simulator to populate this view."}
          </p>
        </div>
      </header>

      {/* BatchDashboard handles its own data source based on demoMode */}
      <BatchDashboard onSelectPayment={setSelected} demoMode={demoMode} refreshKey={refreshKey} />
      <PaymentDetailDrawer payment={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
