import type { EvidenceRef } from "../types/api";

interface EvidenceViewerProps {
  title?: string;
  evidence: EvidenceRef[];
  emptyLabel?: string;
}

const KIND_LABEL: Record<EvidenceRef["kind"], string> = {
  CCD: "CCD file",
  PROCESSING_ENGINE: "Processing engine",
  SETTLEMENT: "Settlement report",
  RETURN: "NACHA return file",
  HISTORICAL: "Historical records",
};

export function EvidenceViewer({
  title = "Evidence",
  evidence,
  emptyLabel = "No evidence attached",
}: EvidenceViewerProps) {
  if (evidence.length === 0) {
    return (
      <section className="evidence">
        <h3 className="evidence__title">{title}</h3>
        <p className="evidence__empty">{emptyLabel}</p>
      </section>
    );
  }

  return (
    <section className="evidence">
      <h3 className="evidence__title">{title}</h3>
      <ul className="evidence__list">
        {evidence.map((e, idx) => (
          <li key={idx} className={`evidence__item evidence__item--${e.kind.toLowerCase()}`}>
            <div className="evidence__kind">{KIND_LABEL[e.kind]}</div>
            {e.sourceFile && <div className="evidence__file">{e.sourceFile}</div>}
            <div className="evidence__summary">{e.summary}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}
