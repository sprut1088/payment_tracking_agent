const STEPS: Array<{ label: string; command?: string; hint: string }> = [
  {
    label: "Reset the demo-inbox folders.",
    command: ".\\scripts\\seed-local-demo-files.ps1 -Phase clean",
    hint: "Clears any previously staged CCD, settlement, scheme-reject, and return files.",
  },
  {
    label: "Seed CCD, then click Scan CCD.",
    command: ".\\scripts\\seed-local-demo-files.ps1 -Phase ccd",
    hint: "Parses the CCD batch and inserts payments as SENT TO SCHEME.",
  },
  {
    label: "Seed settlement and scheme reject, then click Check settlement.",
    command: ".\\scripts\\seed-local-demo-files.ps1 -Phase settlement",
    hint: "Applies scheme reject first, then moves remaining payments to WITH BENEFICIARY BANK. No payment-level clearing is claimed.",
  },
  {
    label: "Seed the NACHA return, then click Check returns.",
    command: ".\\scripts\\seed-local-demo-files.ps1 -Phase returns",
    hint: "Matches the return trace and marks that payment REJECTED BY BENEFICIARY BANK.",
  },
  {
    label:
      "Open Batch Dashboard, Customer Dashboard, or Payment Search to inspect the live ledger.",
    hint: "Each view labels itself as Live backend ledger from parsed CCD and file evidence.",
  },
];

export function LiveFolderRunbook() {
  return (
    <section className="card runbook">
      <header className="card__header">
        <div>
          <div className="page__eyebrow">Runbook</div>
          <h2 className="card__title">Live Folder Demo Runbook</h2>
          <p className="card__subtitle">
            Follow these steps to drive the live backend ledger end-to-end.
            Settlement summary is not payment-level clearing evidence.
          </p>
        </div>
      </header>

      <ol className="runbook__steps">
        {STEPS.map((step, idx) => (
          <li key={idx} className="runbook__step">
            <div className="runbook__step-number">{idx + 1}</div>
            <div className="runbook__step-body">
              <div className="runbook__step-label">{step.label}</div>
              {step.command && (
                <pre className="runbook__command">
                  <code>{step.command}</code>
                </pre>
              )}
              <div className="runbook__step-hint">{step.hint}</div>
            </div>
          </li>
        ))}
      </ol>

      <div className="runbook__final">
        <div className="runbook__final-label">Expected final seeded flow</div>
        <div className="runbook__final-body">
          14 payments with beneficiary bank, 1 rejected by scheme, 1 rejected
          by beneficiary bank. No payment-level clearing is claimed from
          settlement summary.
        </div>
      </div>
    </section>
  );
}
