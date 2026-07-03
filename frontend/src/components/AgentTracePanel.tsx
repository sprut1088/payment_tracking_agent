import type { AgentTraceStep } from "../types/api";

interface AgentTracePanelProps {
  trace: AgentTraceStep[];
  title?: string;
}

export function AgentTracePanel({ trace, title = "Agent trace" }: AgentTracePanelProps) {
  return (
    <section className="card">
      <header className="card__header">
        <h2 className="card__title">{title}</h2>
        <p className="card__subtitle">
          Every step taken by the multi-agent workflow. Real agent execution is
          wired in a later prompt; this trace is mocked.
        </p>
      </header>
      <ol className="agent-trace">
        {trace.map((step) => (
          <li key={step.timestamp + step.action} className="agent-trace__item">
            <div className="agent-trace__time">{step.timestamp}</div>
            <div className="agent-trace__body">
              <div className="agent-trace__head">
                <span className={`agent-trace__agent agent-trace__agent--${agentKey(step.agent)}`}>
                  {step.agent}
                </span>
                <span className="agent-trace__action">{step.action}</span>
              </div>
              <div className="agent-trace__detail">{step.detail}</div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function agentKey(agent: AgentTraceStep["agent"]): string {
  switch (agent) {
    case "BeforePaymentSubmissionAgent":
      return "before";
    case "AfterPaymentSubmissionAgent":
      return "after";
    case "ReturnFileAgent":
      return "return";
    case "PaymentLifecycleOrchestrator":
      return "orch";
    case "AIExplanationAgent":
      return "ai";
  }
}
