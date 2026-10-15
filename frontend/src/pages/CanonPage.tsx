import { useEffect, useState } from "react";

import { api } from "../api";
import type { Canon, CanonChange } from "../types";
import { predicateLabel } from "./Contradictions";
import { useWorkspace } from "./workspaceContext";

const show = (v: unknown) => (v === null || v === undefined ? "—" : String(v));

export default function CanonPage() {
  const { novel } = useWorkspace();
  const [canon, setCanon] = useState<Canon | null>(null);
  const [changes, setChanges] = useState<CanonChange[]>([]);

  useEffect(() => {
    api.canon(novel.id).then(setCanon);
    api.canonChanges(novel.id).then(setChanges);
  }, [novel.id]);

  if (!canon) return <div className="page muted">Loading…</div>;
  return (
    <div className="page">
      <h1>Canon</h1>
      <p className="muted small">
        What the story treats as true: the character sheets plus everything accepted in Review.
        Contradiction checks compare the text against this.
      </p>

      <section className="panel">
        <h2>Timeline</h2>
        {canon.timeline.length === 0 ? (
          <p className="muted small">No accepted events yet.</p>
        ) : (
          <ol className="timeline" data-testid="canon-timeline">
            {canon.timeline.map((e) => (
              <li key={e.id}>
                <span className="day">{e.story_day === null ? "?" : `day ${e.story_day}`}</span>
                <span className={`badge kind-${e.kind}`}>{e.kind.replace("_", " ")}</span>
                {e.description}
                {e.chapter_number !== null && (
                  <span className="muted small"> · ch {e.chapter_number}</span>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>

      <div className="grid-2">
        <section className="panel">
          <h2>World rules</h2>
          {canon.world_rules.length === 0 ? (
            <p className="muted small">None accepted.</p>
          ) : (
            <ul>
              {canon.world_rules.map((r) => (
                <li key={r.id}>{r.statement}</li>
              ))}
            </ul>
          )}
        </section>
        <section className="panel">
          <h2>Open plot threads</h2>
          {canon.plot_threads.length === 0 ? (
            <p className="muted small">None accepted.</p>
          ) : (
            <ul>
              {canon.plot_threads.map((t) => (
                <li key={t.id}>
                  {t.title} <span className="muted small">({t.status}, ch {t.setup_chapter})</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="panel">
          <h2>Locations</h2>
          {canon.locations.length === 0 ? (
            <p className="muted small">None.</p>
          ) : (
            <ul>
              {canon.locations.map((l) => (
                <li key={l.id}>
                  {l.name}
                  {Object.keys(l.travel_days).length > 0 && (
                    <span className="muted small">
                      {" "}
                      · travel times to {Object.keys(l.travel_days).length} places
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="panel">
          <h2>Character sheets</h2>
          <ul>
            {canon.characters.map((c) => (
              <li key={c.id}>
                <strong>{c.name}</strong>{" "}
                <span className="muted small">
                  {Object.entries(c.attributes)
                    .map(([k, v]) => `${predicateLabel(k)}: ${v}`)
                    .join(" · ") || "no canon facts"}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="panel">
        <h2>Change log</h2>
        {changes.length === 0 ? (
          <p className="muted small">No changes yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="facts" data-testid="canon-changes">
              <thead>
                <tr>
                  <th>When</th>
                  <th>What</th>
                  <th>Old</th>
                  <th>New</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {changes.map((c) => (
                  <tr key={c.id}>
                    <td>{new Date(c.created_at).toLocaleString()}</td>
                    <td>
                      {c.entity_type} · {c.field}
                    </td>
                    <td>{show(c.old_value)}</td>
                    <td>{show(c.new_value)}</td>
                    <td>{show(c.note)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
