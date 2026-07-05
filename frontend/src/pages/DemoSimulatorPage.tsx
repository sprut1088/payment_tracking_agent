import { useCallback, useEffect, useRef, useState } from "react";
import { api, computeFileRiskLevel, computeFileRiskReason, invalidatePaymentsCache } from "../api/client";
import { AgentTracePanel } from "../components/AgentTracePanel";
import { CycleTimeline } from "../components/CycleTimeline";
import { LocalFolderDemoControls } from "../components/LocalFolderDemoControls";
import { PaymentStatusBoard } from "../components/PaymentStatusBoard";
import { ScenarioConfigPanel } from "../components/ScenarioConfigPanel";
import type { AgentTraceStep, BusinessStatus, DemoFlowConfig, DemoFlowState, DropFileInfo, EventLogEntry, PaymentRecord, SimulationState, UploadSummary } from "../types/api";

const LIVE_POLL_INTERVAL_S = 10;

interface DemoSimulatorPageProps {
  demoMode: boolean;
}

export function DemoSimulatorPage({ demoMode }: DemoSimulatorPageProps) {
  const [state, setState] = useState<SimulationState | null>(null);
  const [trace, setTrace] = useState<AgentTraceStep[]>([]);
  const [liveSummary, setLiveSummary] = useState<SimulationState["summary"] | null>(null);
  const [livePayments, setLivePayments] = useState<PaymentRecord[]>([]);
  const [liveUploads, setLiveUploads] = useState<UploadSummary[]>([]);
  const [liveEvents, setLiveEvents] = useState<EventLogEntry[]>([]);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");
  const [nextRefreshIn, setNextRefreshIn] = useState<number>(0);
  // Data for LocalFolderDemoControls — fetched together with the rest so all sections update atomically.
  const [liveConfig, setLiveConfig] = useState<DemoFlowConfig | null>(null);
  const [liveFlowState, setLiveFlowState] = useState<DemoFlowState | null>(null);
  const [liveDropFiles, setLiveDropFiles] = useState<DropFileInfo[]>([]);
  const [liveAwaitingReview, setLiveAwaitingReview] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load the static scenario structure once
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

  // Single fetch that updates EVERY live section simultaneously so nothing lags behind.
  const performLiveRefresh = useCallback(() => {
    // Always bypass the payment cache so action-button triggers (scan, check-returns, etc.)
    // immediately reflect backend changes rather than serving an 8-second-old snapshot.
    invalidatePaymentsCache();
    Promise.all([
      api.listPaymentsLive(),
      api.listUploadsLive(),
      api.getEventsLive(),
      api.getDemoFlowConfig(),
      api.getDemoFlowState(),
      api.getUnderReview(),
      api.getDropStatus(),
    ])
      .then(([payments, uploads, events, cfg, flowState, reviewItems, dropStatus]) => {
        setLiveSummary({
          totalPayments: payments.length,
          withBank: payments.filter((p) => p.currentStatus === "WITH BANK").length,
          sentToScheme: payments.filter((p) => p.currentStatus === "SENT TO SCHEME").length,
          withBeneficiaryBank: payments.filter((p) => p.currentStatus === "WITH BENEFICIARY BANK").length,
          rejectedByScheme: payments.filter((p) => p.currentStatus === "REJECTED BY SCHEME").length,
          rejectedByBeneficiaryBank: payments.filter((p) => p.currentStatus === "REJECTED BY BENEFICIARY BANK").length,
        });
        setLivePayments(payments);
        setLiveUploads(uploads);
        setLiveEvents(events);
        setLiveConfig(cfg);
        setLiveFlowState(flowState);
        setLiveDropFiles(dropStatus.files);
        setLiveAwaitingReview(reviewItems.length);
        setLastRefreshed(new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
        setNextRefreshIn(LIVE_POLL_INTERVAL_S);
      })
      .catch(() => {});
  }, []); // all setters are stable — no deps needed

  // When Demo Mode is OFF: run performLiveRefresh immediately then on interval.
  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (demoMode) {
      setLiveSummary(null);
      setLivePayments([]);
      setLiveUploads([]);
      setLiveEvents([]);
      setLiveConfig(null);
      setLiveFlowState(null);
      setLiveDropFiles([]);
      setLiveAwaitingReview(0);
      setNextRefreshIn(0);
      if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = null; }
      return;
    }

    performLiveRefresh();
    intervalRef.current = setInterval(performLiveRefresh, LIVE_POLL_INTERVAL_S * 1000);

    // 1-second countdown tick
    if (countdownRef.current) clearInterval(countdownRef.current);
    countdownRef.current = setInterval(() => {
      setNextRefreshIn((n) => (n > 0 ? n - 1 : 0));
    }, 1000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, [demoMode, performLiveRefresh]);

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
            {demoMode
              ? "Demo Mode ON: showing predefined SME-aligned mock story (11:00 and 11:04 cycles)."
              : "Demo Mode OFF: backend local-folder controls are active below. Dashboards remain mocked for presentation."}
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

      <ScenarioConfigPanel demoMode={demoMode} />

      {demoMode ? (
        <section className="card">
          <header className="card__header">
            <h2 className="card__title">Demo Mode ON</h2>
            <p className="card__subtitle">
              Local-folder backend controls are hidden in this mode. Use the
              top-right toggle to switch OFF Demo Mode and run ensure/scan/check
              actions against backend endpoints.
            </p>
          </header>
        </section>
      ) : (
        <LocalFolderDemoControls
          config={liveConfig}
          flowState={liveFlowState}
          liveUploads={liveUploads}
          livePayments={livePayments}
          dropFiles={liveDropFiles}
          awaitingReviewCount={liveAwaitingReview}
          onRefresh={performLiveRefresh}
        />
      )}

      <div className="grid grid--2">
        <PaymentStatusBoard
          state={
            !demoMode && liveSummary
              ? { ...state, summary: liveSummary }
              : state
          }
          demoMode={demoMode}
          underReviewCount={liveAwaitingReview}
        />
        {demoMode ? (
          <CycleTimeline
            plan={state.plan}
            runs={state.runs}
            activeCycle={state.activeCycle}
          />
        ) : (
          <section className="card">
            <header className="card__header">
              <h2 className="card__title">Live batch activity</h2>
              <p className="card__subtitle">
                CCD files processed by scheduler or Scan CCD.
                Settlement and return events appear in the Live Event Log below.
                {lastRefreshed && <> Last refreshed: <strong>{lastRefreshed}</strong>.</>}
                {nextRefreshIn > 0 && <> Next refresh in <strong>{nextRefreshIn}s</strong>.</>}
              </p>
            </header>
            {liveUploads.length === 0 ? (
              <p className="card__empty">No uploads yet. Drop a CCD file in drop/ccd/input/ or use Scan CCD.</p>
            ) : (
              <ol className="timeline">
                {liveUploads.map((u) => {
                  const uploadPayments = livePayments.filter((p) => p.sourceFile === u.file_name);
                  const fileRiskLevel = computeFileRiskLevel(uploadPayments);
                  const fileRiskReason = computeFileRiskReason(uploadPayments);
                  const statusCounts: Partial<Record<BusinessStatus, number>> = {};
                  for (const p of uploadPayments) {
                    statusCounts[p.currentStatus] = (statusCounts[p.currentStatus] ?? 0) + 1;
                  }
                  const dominated = Object.entries(statusCounts).sort((a, b) => b[1] - a[1])[0]?.[0] as BusinessStatus | undefined;
                  const itemClass = dominated === "WITH BENEFICIARY BANK" || dominated === "REJECTED BY BENEFICIARY BANK"
                    ? "timeline__item--complete"
                    : dominated === "SENT TO SCHEME"
                      ? "timeline__item--active"
                      : "timeline__item--pending";
                  return (
                    <li key={u.upload_id} className={`timeline__item ${itemClass}`}>
                      <div className="timeline__dot" aria-hidden />
                      <div className="timeline__body">
                        <div className="timeline__head">
                          <span className="timeline__time">
                            {new Date(u.uploaded_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                          </span>
                          <span className="timeline__status">
                            {dominated ?? "WITH BANK"}
                          </span>
                        </div>
                        <div className="timeline__label">{u.file_name}</div>
                        <div className="timeline__metrics">
                          <span
                            className={`risk risk--${fileRiskLevel.toLowerCase()}`}
                            data-tooltip={uploadPayments.length > 0 ? fileRiskReason : undefined}
                          >
                            {fileRiskLevel} risk
                          </span>
                          <span>{u.entry_count} payment(s)</span>
                          {Object.entries(statusCounts).map(([s, n]) => (
                            <span key={s}>{s}: {n}</span>
                          ))}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>
        )}
      </div>

      {demoMode ? (
        <>
          <section className="card">
            <header className="card__header">
              <h2 className="card__title">Event log</h2>
              <p className="card__subtitle">
                Latest events emitted in the SME-aligned flow. Settlement entries
                are summary-level evidence and do not claim payment-level clearing.
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
        </>
      ) : (
        <section className="card">
          <header className="card__header">
            <h2 className="card__title">Live event log</h2>
            <p className="card__subtitle">
              Real events emitted by backend agents and scheduler jobs.
              {lastRefreshed && <> Last refreshed: <strong>{lastRefreshed}</strong>.</>}
            </p>
          </header>
          {liveEvents.length === 0 ? (
            <p className="card__empty">No events yet. Upload a CCD file to start the flow.</p>
          ) : (
            <ul className="event-log">
              {liveEvents.map((e, i) => (
                <li key={i} className="event-log__item">
                  <span className="event-log__time">{e.timestamp}</span>
                  <span className="event-log__cycle">{e.cycleTime}</span>
                  <span className="event-log__agent">{e.agent}</span>
                  <span className="event-log__message">{e.message}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
