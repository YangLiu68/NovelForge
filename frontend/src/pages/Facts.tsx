import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { spanHref } from "../spans";
import type { Claim } from "../types";
import { predicateLabel, timeLabel } from "./Contradictions";
import { useWorkspace } from "./workspaceContext";

export default function Facts() {
  const { novel, chapters } = useWorkspace();
  const [claims, setClaims] = useState<Claim[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.claims(novel.id).then(setClaims).catch((e: Error) => setError(e.message));
  }, [novel.id, chapters]);

  return (
    <div className="page">
      <h1>Extracted facts</h1>
      <p className="muted small">
        Proposals from the rule extractor (and the LLM extractor when enabled). They are never written to canon
        automatically. Hedged statements and dialogue get low confidence.
      </p>
      {error && <p className="error">{error}</p>}
      {!claims ? (
        <p className="muted">Loading…</p>
      ) : claims.length === 0 ? (
        <p>No facts extracted yet. Add characters, then write about them by name.</p>
      ) : (
        <div className="table-wrap">
          <table className="facts">
            <thead>
              <tr>
                <th>Character</th>
                <th>Fact</th>
                <th>Value</th>
                <th>Modality</th>
                <th>Conf.</th>
                <th>When</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {claims.map((c) => (
                <tr key={c.id} className={c.modality === "asserted" ? "" : "low"}>
                  <td>{c.subject_name}</td>
                  <td>{predicateLabel(c.predicate)}</td>
                  <td>{c.value}</td>
                  <td>{c.modality}</td>
                  <td>{c.confidence.toFixed(2)}</td>
                  <td>{timeLabel(c)}</td>
                  <td>
                    {c.evidence.map((e) => (
                      <Link
                        key={`${e.chapter_id}-${e.start}`}
                        to={spanHref(novel.id, e.chapter_id, e.start, e.end, e.chapter_version)}
                      >
                        Ch {e.chapter_number}: “{e.quote}”
                      </Link>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
