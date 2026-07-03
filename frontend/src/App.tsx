import { useEffect, useState } from "react";
import { AppShell, type NavKey } from "./components/AppShell";
import { BatchDashboardPage } from "./pages/BatchDashboardPage";
import { CustomerDashboardPage } from "./pages/CustomerDashboardPage";
import { DemoSimulatorPage } from "./pages/DemoSimulatorPage";
import { PaymentSearchPage } from "./pages/PaymentSearchPage";

export default function App() {
  const [nav, setNav] = useState<NavKey>("simulator");
  const [demoMode, setDemoMode] = useState<boolean>(true);

  // Track which pages have ever been visited so we only mount them once.
  // Once mounted they stay alive (hidden via display:none) to preserve their
  // state and avoid re-fetching data on every navigation.
  const [visited, setVisited] = useState<Set<NavKey>>(new Set<NavKey>(["simulator"]));

  useEffect(() => {
    setVisited((prev) => {
      if (prev.has(nav)) return prev;
      return new Set([...prev, nav]);
    });
  }, [nav]);

  const show = (key: NavKey) => ({ style: { display: nav === key ? undefined : "none" } as React.CSSProperties });

  return (
    <AppShell
      activeNav={nav}
      onNavigate={setNav}
      demoMode={demoMode}
      onToggleDemoMode={() => setDemoMode((prev) => !prev)}
    >
      {visited.has("simulator") && (
        <div {...show("simulator")}>
          <DemoSimulatorPage demoMode={demoMode} />
        </div>
      )}
      {visited.has("batch") && (
        <div {...show("batch")}>
          <BatchDashboardPage demoMode={demoMode} isActive={nav === "batch"} />
        </div>
      )}
      {visited.has("customer") && (
        <div {...show("customer")}>
          <CustomerDashboardPage demoMode={demoMode} isActive={nav === "customer"} />
        </div>
      )}
      {visited.has("search") && (
        <div {...show("search")}>
          <PaymentSearchPage demoMode={demoMode} isActive={nav === "search"} />
        </div>
      )}
    </AppShell>
  );
}
