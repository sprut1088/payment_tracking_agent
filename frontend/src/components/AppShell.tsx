import type { ReactNode } from "react";

export type NavKey = "simulator" | "batch" | "customer" | "search";

interface AppShellProps {
  activeNav: NavKey;
  onNavigate: (key: NavKey) => void;
  children: ReactNode;
}

const NAV_ITEMS: Array<{ key: NavKey; label: string; hint: string }> = [
  { key: "simulator", label: "Demo Simulator", hint: "Run cycles and watch the lifecycle" },
  { key: "batch", label: "Batch Dashboard", hint: "Payments grouped by batch" },
  { key: "customer", label: "Customer Dashboard", hint: "Payments grouped by customer" },
  { key: "search", label: "Payment Search", hint: "Find one payment and its evidence" },
];

export function AppShell({ activeNav, onNavigate, children }: AppShellProps) {
  return (
    <div className="shell">
      <aside className="shell__sidebar">
        <div className="shell__brand">
          <div className="shell__brand-mark">ACH</div>
          <div>
            <div className="shell__brand-title">Payment Tracking Agent</div>
            <div className="shell__brand-subtitle">Operations console · Demo</div>
          </div>
        </div>
        <nav className="shell__nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              type="button"
              className={
                "shell__nav-item" + (item.key === activeNav ? " shell__nav-item--active" : "")
              }
              onClick={() => onNavigate(item.key)}
            >
              <span className="shell__nav-label">{item.label}</span>
              <span className="shell__nav-hint">{item.hint}</span>
            </button>
          ))}
        </nav>
        <div className="shell__footer">
          <div className="shell__footer-title">Demo mode</div>
          <div className="shell__footer-body">
            All data below is mocked in the frontend. Backend, ledger, and LLM
            logic are implemented in later build steps.
          </div>
        </div>
      </aside>
      <main className="shell__main">{children}</main>
    </div>
  );
}
