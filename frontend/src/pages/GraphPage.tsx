import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { forceLayout } from "../layout";
import { spanHref } from "../spans";
import type { GraphEdge, GraphNode, TimelineData, TimelineEvent } from "../types";
import { predicateLabel } from "./Contradictions";
import { useWorkspace } from "./workspaceContext";

const FAMILY_COLOR: Record<string, string> = {
  location: "var(--fam-location)",
  status: "var(--fam-status)",
  ability: "var(--fam-ability)",
  attribute: "var(--fam-attribute)",
  age: "var(--fam-age)",
  other: "var(--muted)",
};

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(800);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

function CharacterGraph({ nodes, edges }: { nodes: GraphNode[]; edges: GraphEdge[] }) {
  const { novel } = useWorkspace();
  const [ref, width] = useWidth<HTMLDivElement>();
  const height = Math.max(380, Math.min(620, width * 0.62));
  const [hover, setHover] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ node?: GraphNode; edge?: GraphEdge } | null>(null);

  const ordered = useMemo(
    () => [...nodes].sort((a, b) => b.mentions - a.mentions || a.name.localeCompare(b.name)),
    [nodes],
  );
  const pos = useMemo(
    () =>
      forceLayout(
        ordered.map((n) => ({ id: n.id, weight: n.mentions })),
        edges.map((e) => ({ source: e.source, target: e.target, weight: e.weight })),
        width,
        height,
      ),
    [ordered, edges, width, height],
  );
  const maxMentions = Math.max(1, ...nodes.map((n) => n.mentions));
  const maxWeight = Math.max(1, ...edges.map((e) => e.weight));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const neighbours = new Set(
    edges
      .filter((e) => hover && (e.source === hover || e.target === hover))
      .flatMap((e) => [e.source, e.target]),
  );
  const radius = (n: GraphNode) => 7 + 15 * Math.sqrt(n.mentions / maxMentions);

  return (
    <div className="graph-layout">
      <div ref={ref} className="graph-canvas">
        <svg
          width="100%"
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label="Character co-occurrence graph"
          data-testid="character-graph"
        >
          {edges.map((e) => {
            const a = pos.get(e.source);
            const b = pos.get(e.target);
            if (!a || !b) return null;
            const dim = hover && !(e.source === hover || e.target === hover);
            return (
              <line
                key={`${e.source}-${e.target}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                className={`edge ${e.relationships.length ? "rel" : ""} ${dim ? "dim" : ""}`}
                strokeWidth={1 + (4 * e.weight) / maxWeight}
                onClick={() => setSelected({ edge: e })}
              >
                <title>
                  {byId.get(e.source)?.name} & {byId.get(e.target)?.name}: together in {e.weight}{" "}
                  paragraphs{e.relationships.length ? ` · ${e.relationships.join(", ")}` : ""}
                </title>
              </line>
            );
          })}
          {ordered.map((n) => {
            const p = pos.get(n.id);
            if (!p) return null;
            const dim = hover && hover !== n.id && !neighbours.has(n.id);
            return (
              <g
                key={n.id}
                className={`node ${dim ? "dim" : ""} ${selected?.node?.id === n.id ? "selected" : ""}`}
                transform={`translate(${p.x},${p.y})`}
                onMouseEnter={() => setHover(n.id)}
                onMouseLeave={() => setHover(null)}
                onClick={() => setSelected({ node: n })}
                data-testid="graph-node"
              >
                <circle r={radius(n)} />
                <text y={radius(n) + 13} textAnchor="middle">
                  {n.name}
                </text>
                <title>
                  {n.name}: mentioned in {n.mentions} paragraphs
                </title>
              </g>
            );
          })}
        </svg>
      </div>
      <aside className="panel graph-side" data-testid="graph-details">
        {!selected && (
          <p className="muted small">
            Circle size: how many paragraphs mention the character. Line thickness: how often two
            characters appear in the same paragraph; dashed lines are accepted relationships.
            Click a circle or a line for details.
          </p>
        )}
        {selected?.node && (
          <>
            <h3>{selected.node.name}</h3>
            <p className="muted small">
              {selected.node.mentions} paragraphs · first in chapter{" "}
              {selected.node.first_chapter ?? "?"}
            </p>
            <dl className="attrs">
              {Object.entries(selected.node.attributes).map(([k, v]) => (
                <div key={k}>
                  <dt>{predicateLabel(k)}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
            <h4>Most often with</h4>
            <ul>
              {edges
                .filter((e) => e.source === selected.node!.id || e.target === selected.node!.id)
                .sort((a, b) => b.weight - a.weight)
                .slice(0, 6)
                .map((e) => {
                  const other = byId.get(e.source === selected.node!.id ? e.target : e.source);
                  return (
                    <li key={`${e.source}-${e.target}`}>
                      <button className="link" onClick={() => setSelected({ edge: e })}>
                        {other?.name}
                      </button>{" "}
                      <span className="muted small">{e.weight}×</span>
                    </li>
                  );
                })}
            </ul>
          </>
        )}
        {selected?.edge && (
          <>
            <h3>
              {byId.get(selected.edge.source)?.name} & {byId.get(selected.edge.target)?.name}
            </h3>
            <p className="muted small">
              Together in {selected.edge.weight} paragraphs
              {selected.edge.relationships.length > 0 &&
                ` · ${selected.edge.relationships.join(", ")}`}
            </p>
            {selected.edge.samples.map((s) => (
              <Link
                key={`${s.chapter_id}-${s.start}`}
                to={spanHref(novel.id, s.chapter_id, s.start, s.end, s.chapter_version)}
                className="evidence-link"
              >
                Ch {s.chapter_number}: <span className="quote">{s.quote}…</span>
              </Link>
            ))}
          </>
        )}
      </aside>
    </div>
  );
}

function Timeline({ data }: { data: TimelineData }) {
  const { novel } = useWorkspace();
  const navigate = useNavigate();
  const [ref, width] = useWidth<HTMLDivElement>();
  const [axis, setAxis] = useState<"day" | "chapter">("chapter");
  const [showAll, setShowAll] = useState(false);
  const lanes = showAll ? data.lanes : data.lanes.slice(0, 12);
  const left = 130;
  const right = 20;
  const laneH = 34;
  const top = 26;
  const height = top + lanes.length * laneH + 20;
  const chapterIndex = new Map(data.chapters.map((c, i) => [c.number, i]));
  const n = Math.max(1, data.chapters.length - 1);
  const [d0, d1] = data.day_range ?? [0, 1];
  const span = Math.max(1, d1 - d0);
  const x = (e: TimelineEvent) =>
    axis === "chapter"
      ? left + ((chapterIndex.get(e.chapter_number ?? 0) ?? 0) / n) * (width - left - right)
      : left + ((e.day - d0) / span) * (width - left - right);
  // Facts that land on the same spot (same lane, same chapter or day) are spread a few pixels
  // apart so every dot stays visible and clickable.
  const point = new Map<string, { x: number; y: number }>();
  lanes.forEach((lane, i) => {
    const groups = new Map<number, TimelineEvent[]>();
    for (const e of lane.events) {
      const key = Math.round(x(e));
      groups.set(key, [...(groups.get(key) ?? []), e]);
    }
    for (const [key, events] of groups) {
      const spread = Math.min(10, 40 / events.length);
      events.forEach((e, j) =>
        point.set(e.claim_id, {
          x: key + (j - (events.length - 1) / 2) * spread,
          y: top + i * laneH + laneH / 2,
        }),
      );
    }
  });
  const flagged = new Set(data.findings.flatMap((f) => f.claim_ids));

  return (
    <div>
      <div className="toolbar">
        <div className="segmented" role="radiogroup" aria-label="Time axis">
          <button
            role="radio"
            aria-checked={axis === "chapter"}
            className={axis === "chapter" ? "seg active" : "seg"}
            onClick={() => setAxis("chapter")}
          >
            Chapter order
          </button>
          <button
            role="radio"
            aria-checked={axis === "day"}
            className={axis === "day" ? "seg active" : "seg"}
            onClick={() => setAxis("day")}
          >
            Story day
          </button>
        </div>
        <div className="legend small">
          {Object.entries(FAMILY_COLOR)
            .filter(([k]) => k !== "other")
            .map(([k, c]) => (
              <span key={k}>
                <span className="swatch" style={{ background: c }} /> {k}
              </span>
            ))}
          <span>
            <span className="swatch conflict" /> contradiction
          </span>
        </div>
      </div>
      <div ref={ref} className="timeline-canvas">
        <svg
          width="100%"
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label="Character timeline"
          data-testid="timeline"
        >
          <text x={left} y={14} className="axis-label">
            {axis === "chapter" ? `chapter ${data.chapters[0]?.number ?? ""}` : `day ${d0}`}
          </text>
          <text x={width - right} y={14} className="axis-label" textAnchor="end">
            {axis === "chapter"
              ? `chapter ${data.chapters[data.chapters.length - 1]?.number ?? ""}`
              : `day ${d1}`}
          </text>
          {lanes.map((lane, i) => (
            <g key={lane.character_id}>
              <line
                x1={left}
                x2={width - right}
                y1={top + i * laneH + laneH / 2}
                y2={top + i * laneH + laneH / 2}
                className="lane"
              />
              <text x={left - 8} y={top + i * laneH + laneH / 2 + 4} textAnchor="end" className="lane-label">
                {lane.name}
              </text>
            </g>
          ))}
          {data.findings.map((f) => {
            const pts = f.claim_ids.map((id) => point.get(id)).filter(Boolean) as {
              x: number;
              y: number;
            }[];
            if (pts.length < 2) return null;
            const [a, b] = [pts[0], pts[pts.length - 1]];
            const lift = a.y === b.y ? Math.min(16, Math.abs(b.x - a.x) / 4 + 6) : 0;
            return (
              <path
                key={f.id}
                d={`M${a.x},${a.y} Q${(a.x + b.x) / 2},${Math.min(a.y, b.y) - lift} ${b.x},${b.y}`}
                className="conflict-link"
                onClick={() => navigate(`/novels/${novel.id}/contradictions`)}
                data-testid="timeline-conflict"
              >
                <title>{f.explanation}</title>
              </path>
            );
          })}
          {lanes.flatMap((lane) =>
            lane.events.map((e) => {
              const p = point.get(e.claim_id)!;
              return (
                <circle
                  key={e.claim_id}
                  cx={p.x}
                  cy={p.y}
                  r={flagged.has(e.claim_id) ? 6 : 4.5}
                  className={`event ${flagged.has(e.claim_id) ? "flagged" : ""}`}
                  style={{ fill: FAMILY_COLOR[e.family] }}
                  onClick={() =>
                    e.start !== null &&
                    navigate(
                      spanHref(novel.id, e.chapter_id, e.start, e.end!, e.chapter_version ?? undefined),
                    )
                  }
                  data-testid="timeline-event"
                >
                  <title>
                    {lane.name} · {predicateLabel(e.predicate)}: {e.value} · day {e.day} · ch{" "}
                    {e.chapter_number}
                    {"\n"}“{e.quote}”
                  </title>
                </circle>
              );
            }),
          )}
        </svg>
      </div>
      <p className="muted small">
        {data.undated_claims > 0 && `${data.undated_claims} facts have no known story day and are not shown. `}
        {data.lanes.length > 12 && (
          <button className="link" onClick={() => setShowAll(!showAll)}>
            {showAll ? "Show top 12 characters" : `Show all ${data.lanes.length} characters`}
          </button>
        )}
      </p>
    </div>
  );
}

export default function GraphPage() {
  const { novel, chapters } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "timeline" ? "timeline" : "graph";
  const [graph, setGraph] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
  const [timeline, setTimeline] = useState<TimelineData | null>(null);

  useEffect(() => {
    api.graph(novel.id).then(setGraph);
    api.timeline(novel.id).then(setTimeline);
  }, [novel.id, chapters]);

  return (
    <div className="page wide">
      <h1>Characters & timeline</h1>
      <div className="segmented" role="radiogroup" aria-label="View">
        <button
          role="radio"
          aria-checked={view === "graph"}
          className={view === "graph" ? "seg active" : "seg"}
          onClick={() => setParams({ view: "graph" })}
        >
          Character graph
        </button>
        <button
          role="radio"
          aria-checked={view === "timeline"}
          className={view === "timeline" ? "seg active" : "seg"}
          onClick={() => setParams({ view: "timeline" })}
        >
          Timeline
        </button>
      </div>
      {view === "graph" ? (
        graph ? (
          <CharacterGraph nodes={graph.nodes} edges={graph.edges} />
        ) : (
          <p className="muted">Loading…</p>
        )
      ) : timeline ? (
        timeline.lanes.length ? (
          <Timeline data={timeline} />
        ) : (
          <p className="muted">No dated facts yet. Give chapters a story day to see a timeline.</p>
        )
      ) : (
        <p className="muted">Loading…</p>
      )}
    </div>
  );
}
