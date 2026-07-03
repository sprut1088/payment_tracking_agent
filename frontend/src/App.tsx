import { useState } from "react";
import { AppShell, type NavKey } from "./components/AppShell";
import { BatchDashboardPage } from "./pages/BatchDashboardPage";
import { CustomerDashboardPage } from "./pages/CustomerDashboardPage";
import { DemoSimulatorPage } from "./pages/DemoSimulatorPage";
import { PaymentSearchPage } from "./pages/PaymentSearchPage";

export default function App() {
  const [nav, setNav] = useState<NavKey>("simulator");

  return (
    <AppShell activeNav={nav} onNavigate={setNav}>
      {nav === "simulator" && <DemoSimulatorPage />}
      {nav === "batch" && <BatchDashboardPage />}
      {nav === "customer" && <CustomerDashboardPage />}
      {nav === "search" && <PaymentSearchPage />}
    </AppShell>
  );
}
