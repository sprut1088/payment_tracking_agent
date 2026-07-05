/**
 * CcdReviewPanel — shows CCD files awaiting correction review.
 *
 * For each under-review file the panel renders a line-by-line diff table that
 * highlights corrected lines.  The user can Accept (submit corrections through
 * the upload pipeline) or Reject (discard the file) each entry.
 */
import { useState } from "react";
import { api } from "../api/client";
import type { UnderReviewItem } from "../types/api";

interface CcdReviewPanelProps {
  items: UnderReviewItem[];
  onReviewed: () => void; // called after every accept / reject so the parent can refresh
}

function buildOriginalLines(content: string): string[] {
  return content.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
}

interface DiffRow {
  lineNum: number;
  kind: "context" | "removed" | "added";
  text: string;
  explanation?: string | null;
}

function buildDiffRows(item: UnderReviewItem): DiffRow[] {
  const origLines = buildOriginalLines(item.original_content);
  const correctedMap = new Map<number, { line: string; explanation?: string | null }>();
  for (const cl of item.corrected_lines ?? []) {
    if (cl.was_corrected) {
      correctedMap.set(cl.line_number, { line: cl.line, explanation: cl.explanation });
    }
  }

  const rows: DiffRow[] = [];
  for (let i = 0; i < origLines.length; i++) {
    const lineNum = i + 1;
    const correction = correctedMap.get(lineNum);
    if (correction) {
      rows.push({ lineNum, kind: "removed", text: origLines[i] });
      rows.push({ lineNum, kind: "added", text: correction.line, explanation: correction.explanation });
    } else {
      rows.push({ lineNum, kind: "context", text: origLines[i] });
    }
  }
  return rows;
}

function DiffTable({ item }: { item: UnderReviewItem }) {
  const rows = buildDiffRows(item);
  const hasCorrections = (item.corrected_lines ?? []).some((l) => l.was_corrected);

  if (!hasCorrections) {
    return (
      <div className="review-diff">
        <p className="review-diff__note">No auto-corrections available. Review the errors listed above.</p>
      </div>
    );
  }

  return (
    <div className="review-diff">
      <div className="review-diff__legend">
        <span className="review-diff__legend-item review-diff__legend-item--removed">− original</span>
        <span className="review-diff__legend-item review-diff__legend-item--added">+ corrected</span>
        <span className="review-diff__legend-hint">Hover a corrected line to see what changed</span>
      </div>
      <div className="review-diff__scroll">
        <table className="review-diff__table">
          <tbody>
            {rows.map((row, idx) => (
              <tr
                key={idx}
                className={`review-diff__row review-diff__row--${row.kind}`}
                title={row.kind === "added" && row.explanation ? row.explanation : undefined}
              >
                <td className="review-diff__gutter">
                  {row.kind === "removed" ? "−" : row.kind === "added" ? "+" : " "}
                </td>
                <td className="review-diff__ln">{row.lineNum}</td>
                <td className="review-diff__code">{row.text}</td>
                {row.kind === "added" && row.explanation && (
                  <td className="review-diff__expl">{row.explanation}</td>
                )}
                {!(row.kind === "added" && row.explanation) && (
                  <td className="review-diff__expl" />
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ReviewCard({
  item,
  onAccepted,
  onRejected,
}: {
  item: UnderReviewItem;
  onAccepted: () => void;
  onRejected: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [cardError, setCardError] = useState<string | null>(null);

  const correctedCount = item.corrected_lines?.filter((l) => l.was_corrected).length ?? 0;

  const handleAccept = async () => {
    if (!item.corrected_file_content) return;
    setBusy(true);
    setCardError(null);
    try {
      await api.acceptCorrection({
        batch_id: item.batch_id,
        file_name: item.file_name,
        corrected_content: item.corrected_file_content,
      });
      onAccepted();
    } catch (err: unknown) {
      setCardError(err instanceof Error ? err.message : "Accept failed.");
      setBusy(false);
    }
  };

  const handleReject = async () => {
    setBusy(true);
    setCardError(null);
    try {
      await api.rejectCorrection({ batch_id: item.batch_id, file_name: item.file_name });
      onRejected();
    } catch (err: unknown) {
      setCardError(err instanceof Error ? err.message : "Reject failed.");
      setBusy(false);
    }
  };

  return (
    <div className="review-card">
      <div className="review-card__header">
        <div className="review-card__meta">
          <span className="review-card__filename">{item.file_name}</span>
          <span className="badge badge--warning">Awaiting Review</span>
          <span className="review-card__counts">
            {item.errors.length} error{item.errors.length !== 1 ? "s" : ""}
            {correctedCount > 0 && ` · ${correctedCount} line${correctedCount !== 1 ? "s" : ""} auto-corrected`}
          </span>
        </div>
        <div className="review-card__actions">
          <button
            type="button"
            className="button button--sm button--ghost"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Hide diff" : "Show diff"}
          </button>
          {item.corrected_file_content ? (
            <button
              type="button"
              className="button button--sm button--primary"
              disabled={busy}
              onClick={() => void handleAccept()}
            >
              Accept corrections
            </button>
          ) : (
            <span
              className="review-card__no-corrections"
              data-tooltip="No auto-corrections available — LLM not configured or corrections could not be generated. Edit the file manually and re-upload."
            >
              No auto-corrections
            </span>
          )}
          <button
            type="button"
            className="button button--sm button--danger"
            disabled={busy}
            onClick={() => void handleReject()}
          >
            Reject
          </button>
        </div>
      </div>

      {item.errors.length > 0 && (
        <ul className="review-card__errors">
          {item.errors.map((e, i) => (
            <li key={i} className="review-card__error-item">
              {e}
            </li>
          ))}
        </ul>
      )}

      {cardError && <div className="card__error">{cardError}</div>}

      {expanded && <DiffTable item={item} />}
    </div>
  );
}

export function CcdReviewPanel({ items, onReviewed }: CcdReviewPanelProps) {
  if (items.length === 0) return null;

  return (
    <section className="card">
      <header className="card__header">
        <h2 className="card__title">
          Review queue
          <span className="badge badge--warning" style={{ marginLeft: "0.5rem" }}>
            {items.length} awaiting review
          </span>
        </h2>
        <p className="card__subtitle">
          These CCD files failed validation. Auto-corrections have been generated.
          Accept to load the corrected payments into the ledger, or Reject to discard.
        </p>
      </header>

      <div className="review-list">
        {items.map((item) => (
          <ReviewCard
            key={item.batch_id}
            item={item}
            onAccepted={onReviewed}
            onRejected={onReviewed}
          />
        ))}
      </div>
    </section>
  );
}
