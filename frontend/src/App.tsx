import { useState } from "react";
import { AppShell, type NavKey } from "./components/AppShell";
import { BatchDashboardPage } from "./pages/BatchDashboardPage";
import { CustomerDashboardPage } from "./pages/CustomerDashboardPage";
import { DemoSimulatorPage } from "./pages/DemoSimulatorPage";
import { PaymentSearchPage } from "./pages/PaymentSearchPage";

export default function App() {
  const [nav, setNav] = useState<NavKey>("simulator");
  const [demoMode, setDemoMode] = useState<boolean>(true);

  return (
    <AppShell
      activeNav={nav}
      onNavigate={setNav}
      demoMode={demoMode}
      onToggleDemoMode={() => setDemoMode((prev) => !prev)}
    >
      {nav === "simulator" && <DemoSimulatorPage demoMode={demoMode} />}
      {nav === "batch" && <BatchDashboardPage demoMode={demoMode} />}
      {nav === "customer" && <CustomerDashboardPage demoMode={demoMode} />}
      {nav === "search" && <PaymentSearchPage demoMode={demoMode} />}
    </AppShell>
  );
}
