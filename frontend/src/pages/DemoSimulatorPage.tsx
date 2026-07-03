import { useEffect, useState } from "react";
import { api } from "../api/client";
import { AgentTracePanel } from "../components/AgentTracePanel";
import { CycleTimeline } from "../components/CycleTimeline";
import { PaymentStatusBoard } from "../components/PaymentStatusBoard";
import { ScenarioConfigPanel } from "../components/ScenarioConfigPanel";
import type { AgentTraceStep, SimulationState } from "../types/api";

export function DemoSimulatorPage() {
  const [state, setState] = useState<SimulationState | null>(null);
  const [trace, setTrace] = useState<AgentTraceStep[]>([]);

  useEffect(() => {
    let mounted = true;
    Promise.all([api.getSimulationState(), api.getAgentTrace()]).then(
      ([s, t]) => {
        if (!mounted) return;
        setState(s);
        setTrace(t);
      },
    );
    return () => {
      mounted = false;
    };
  }, []);

  if (!state) {
    return (
      <div className="page">
        <div className="page__loading">Loading simulator…</div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <div className="page__eyebrow">Simulator</div>
          <h1 className="page__title">Demo Simulator</h1>
          <p className="page__subtitle">
            Drive the ACH payment lifecycle across configurable batch cycles and
            watch the multi-agent workflow update the payment status ledger.
          </p>
        </div>
        <div className="clock">
          <div className="clock__label">Current sim time</div>
          <div className="clock__value">{state.currentSimTime}</div>
          {state.activeCycle && (
            <div className="clock__meta">Active cycle {state.activeCycle}</div>
          )}
        </div>
      </header>

      <ScenarioConfigPanel />

      <div className="grid grid--2">
        <PaymentStatusBoard state={state} />
        <CycleTimeline
          plan={state.plan}
          runs={state.runs}
          activeCycle={state.activeCycle}
        />
      </div>

      <section className="card">
        <header className="card__header">
          <h2 className="card__title">Event log</h2>
          <p className="card__subtitle">
            Latest events emitted during the cycles run so far.
          </p>
        </header>
        <ul className="event-log">
          {state.events.map((e, i) => (
            <li key={i} className="event-log__item">
              <span className="event-log__time">{e.timestamp}</span>
              <span className="event-log__cycle">{e.cycleTime}</span>
              <span className="event-log__agent">{e.agent}</span>
              <span className="event-log__message">{e.message}</span>
            </li>
          ))}
        </ul>
      </section>

      <AgentTracePanel trace={trace} />
    </div>
  );
}
