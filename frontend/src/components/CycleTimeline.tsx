import type { CyclePlanEntry, CycleRunSummary } from "../types/api";

interface CycleTimelineProps {
  plan: CyclePlanEntry[];
  runs: CycleRunSummary[];
  activeCycle?: string;
}

export function CycleTimeline({ plan, runs, activeCycle }: CycleTimelineProps) {
  const runByCycle = new Map(runs.map((r) => [r.cycleTime, r]));

  return (
    <section className="card">
      <header className="card__header">
        <h2 className="card__title">Cycle timeline</h2>
        <p className="card__subtitle">
          Configured cycles for this scenario. Each dot represents one batch
          cycle. Real bank cycles are 10:00 / 14:00 / 18:00 GMT; the demo
          accelerates them.
        </p>
      </header>
      <ol className="timeline">
        {plan.map((entry) => {
          const run = runByCycle.get(entry.cycleTime);
          const state =
            run?.status === "COMPLETE"
              ? "timeline__item--complete"
              : entry.cycleTime === activeCycle
                ? "timeline__item--active"
                : "timeline__item--pending";
          return (
            <li key={entry.cycleTime} className={`timeline__item ${state}`}>
              <div className="timeline__dot" aria-hidden />
              <div className="timeline__body">
                <div className="timeline__head">
                  <span className="timeline__time">{entry.cycleTime}</span>
                  <span className="timeline__status">
                    {run?.status ?? "PENDING"}
                  </span>
                </div>
                <div className="timeline__label">{entry.label}</div>
                {(entry.ccdFile || entry.returnFile) && (
                  <div className="timeline__meta">
                    {entry.ccdFile && <span>CCD: {entry.ccdFile}</span>}
                    {entry.returnFile && <span>Return: {entry.returnFile}</span>}
                  </div>
                )}
                {run && run.status === "COMPLETE" && (
                  <div className="timeline__metrics">
                    <span>+{run.paymentsCreated} payments</span>
                    <span>{run.cleared} cleared</span>
                    <span>{run.withBeneficiaryBank} held</span>
                    {run.rejectedFromPriorCycle > 0 && (
                      <span>
                        {run.rejectedFromPriorCycle} prior rejected by return
                      </span>
                    )}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
