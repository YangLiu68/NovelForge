import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { spanHref } from "../spans";
import type { Evidence, Report } from "../types";
import { useWorkspace } from "./workspaceContext";

const KIND_LABEL: Record<string, string> = {
  attribute_conflict: "Conflicting statements",
  canon_conflict: "Contradicts character sheet",
  age_timeline: "Age vs. timeline",
};

const PREDICATE_LABEL: Record<string, string> = {
  eye_color: "eye colour",
  hair_color: "hair colour",
  handedness: "handedness",
  birthplace: "birthplace",
  age: "age",
};

export const predicateLabel = (p: string) => PREDICATE_LABEL[p] ?? p.replaceAll("_", " ");

export function timeLabel(e: { effective_day: number | null; time_certainty: string }) {
  return e.effective_day === null ? "time unknown" : `story day ${e.effective_day}`;
}

function EvidenceItem({ novelId, e }: { novelId: string; e: Evidence }) {
  return (
    <li className="evidence">
      <Link
        to={spanHref(novelId, e.chapter_id, e.start, e.end, e.chapter_version)}
        className="evidence-link"
        data-testid="evidence-link"
      >
        <span className="quote">“{e.quote}”</span>
      </Link>
      <span className="muted small">
        Ch {e.chapter_number} · {e.chapter_title} · {timeLabel(e)} · value “{e.value}”
        {e.modality !== "asserted" && ` · ${e.modality}`}
      </span>
    </li>
  );
}

export default function Contradictions() {
  const { novel, chapters } = useWorkspace();
  const [includeLow, setIncludeLow] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setReport(null);
    api
      .contradictions(novel.id, includeLow ? 0.3 : undefined)
      .then(setReport)
      .catch((e: Error) => setError(e.message));
    // Re-run when chapters change (an edit re-extracts facts).
  }, [novel.id, includeLow, chapters]);

  return (
    <div className="page">
      <h1>Contradictions</h1>
      <p className="muted small">
        Checks facts extracted by the rule-based baseline extractor (rules-v1): eye and hair
        colour, age, handedness and birthplace stated next to a character's name or alias. It
        does not follow pronouns, so some contradictions are missed.
      </p>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={includeLow}
          onChange={(e) => setIncludeLow(e.target.checked)}
        />
        Include hedged statements and dialogue (“seemed”, quoted speech)
      </label>
      {error && <p className="error">{error}</p>}
      {!report ? (
        <p className="muted">Checking…</p>
      ) : (
        <>
          <p className="muted small" data-testid="report-summary">
            {report.findings.length} finding{report.findings.length === 1 ? "" : "s"} from{" "}
            {report.claims_considered} extracted facts · confidence ≥ {report.min_confidence} ·{" "}
            {report.took_ms} ms
          </p>
          {report.findings.length === 0 && <p>No contradictions found.</p>}
          <ul className="card-list">
            {report.findings.map((f) => (
              <li key={f.id} className={`card finding sev-${f.severity}`} data-testid="finding">
                <div className="finding-head">
                  <span className={`badge sev-${f.severity}`}>{f.severity}</span>
                  <span className="finding-kind">{KIND_LABEL[f.kind] ?? f.kind}</span>
                  <span className="muted small">
                    {f.subject_name} · {predicateLabel(f.predicate)} · {f.category}
                  </span>
                </div>
                <p className="explanation">{f.explanation}</p>
                <ul className="evidence-list">
                  {f.canon_value !== null && (
                    <li className="evidence">
                      <Link to={`/novels/${novel.id}/characters`} className="evidence-link">
                        Character sheet: {predicateLabel(f.predicate)} = “{f.canon_value}”
                      </Link>
                    </li>
                  )}
                  {f.evidence.map((e) => (
                    <EvidenceItem key={`${e.claim_id}-${e.start}`} novelId={novel.id} e={e} />
                  ))}
                </ul>
                <p className="suggestion">
                  <strong>Suggestion:</strong> {f.suggestion}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
