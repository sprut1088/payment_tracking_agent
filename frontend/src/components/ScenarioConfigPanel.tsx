import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Scenario } from "../types/api";

interface ScenarioConfigPanelProps {
  demoMode?: boolean;
  onScenarioChange?: (scenarioId: string) => void;
  onRunNextCycle?: () => void;
  onReset?: () => void;
}

export function ScenarioConfigPanel({
  demoMode = true,
  onScenarioChange,
  onRunNextCycle,
  onReset,
}: ScenarioConfigPanelProps) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selected, setSelected] = useState<string>("");

  useEffect(() => {
    let mounted = true;
    api.listScenarios().then((s) => {
      if (!mounted) return;
      setScenarios(s);
      if (s.length > 0) {
        setSelected(s[0].id);
        onScenarioChange?.(s[0].id);
      }
    });
    return () => {
      mounted = false;
    };
  }, [onScenarioChange]);

  const current = scenarios.find((s) => s.id === selected);

  return (
    <section className="card">
      <header className="card__header">
        <h2 className="card__title">Scenario configuration</h2>
        <p className="card__subtitle">
          Choose a scenario and drive the demo cycle by cycle. Times are
          configurable; the platform does not hard-code the three real GMT
          cycles.
        </p>
      </header>
      <div className="scenario-grid">
        <label className="field">
          <span className="field__label">Scenario</span>
          <select
            className="field__control"
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              onScenarioChange?.(e.target.value);
            }}
          >
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field__label">Cycle mode</span>
          <input
            className="field__control"
            readOnly
            value={current?.mode.replaceAll("_", " ") ?? "—"}
          />
        </label>
        <label className="field field--wide">
          <span className="field__label">Cycle schedule</span>
          <input
            className="field__control"
            readOnly
            value={current?.cycleSchedule.join(", ") ?? ""}
          />
        </label>
      </div>
      {current && <p className="scenario-description">{current.description}</p>}
      <div className="action-row">
        <button
          type="button"
          className="button button--primary"
          onClick={() => onRunNextCycle?.()}
        >
          Run next cycle
        </button>
        <button type="button" className="button" onClick={() => onReset?.()}>
          Reset simulation
        </button>
        <span className="action-row__hint">
          {demoMode
            ? "Demo Mode ON: scripted SME-aligned mock story."
            : "Demo Mode OFF: use local-folder backend controls below for real ensure/scan/check actions."}
        </span>
      </div>
    </section>
  );
}
