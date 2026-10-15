// Deterministic force-directed layout (Fruchterman–Reingold) for small graphs (≤ ~100 nodes).
// No randomness: nodes start on a circle in the given order, so the same graph always renders
// the same picture.

export interface LayoutNode {
  id: string;
  weight: number;
}

export interface LayoutEdge {
  source: string;
  target: string;
  weight: number;
}

export function forceLayout(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  width: number,
  height: number,
  iterations = 300,
): Map<string, { x: number; y: number }> {
  const n = nodes.length;
  const pos = new Map<string, { x: number; y: number }>();
  if (n === 0) return pos;
  const cx = width / 2;
  const cy = height / 2;
  const r = Math.min(width, height) * 0.38;
  nodes.forEach((node, i) => {
    const a = (2 * Math.PI * i) / n;
    pos.set(node.id, { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });
  });
  if (n === 1) return pos;
  const k = Math.sqrt((width * height) / n) * 0.75;
  const maxW = Math.max(1, ...edges.map((e) => e.weight));
  let temperature = width / 8;
  for (let it = 0; it < iterations; it++) {
    const disp = new Map(nodes.map((node) => [node.id, { x: 0, y: 0 }]));
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = pos.get(nodes[i].id)!;
        const b = pos.get(nodes[j].id)!;
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let d = Math.hypot(dx, dy);
        if (d < 0.01) {
          dx = 0.01 * (i - j);
          dy = 0.01;
          d = Math.hypot(dx, dy);
        }
        const f = (k * k) / d;
        const da = disp.get(nodes[i].id)!;
        const db = disp.get(nodes[j].id)!;
        da.x += (dx / d) * f;
        da.y += (dy / d) * f;
        db.x -= (dx / d) * f;
        db.y -= (dy / d) * f;
      }
    }
    for (const e of edges) {
      const a = pos.get(e.source);
      const b = pos.get(e.target);
      if (!a || !b) continue;
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const d = Math.max(Math.hypot(dx, dy), 0.01);
      const f = ((d * d) / k) * (0.3 + (0.7 * e.weight) / maxW);
      const da = disp.get(e.source)!;
      const db = disp.get(e.target)!;
      da.x -= (dx / d) * f;
      da.y -= (dy / d) * f;
      db.x += (dx / d) * f;
      db.y += (dy / d) * f;
    }
    for (const node of nodes) {
      const p = pos.get(node.id)!;
      const d = disp.get(node.id)!;
      d.x += (cx - p.x) * 0.02; // gentle gravity keeps disconnected nodes on screen
      d.y += (cy - p.y) * 0.02;
      const len = Math.max(Math.hypot(d.x, d.y), 0.01);
      p.x += (d.x / len) * Math.min(len, temperature);
      p.y += (d.y / len) * Math.min(len, temperature);
      p.x = Math.min(width - 40, Math.max(40, p.x));
      p.y = Math.min(height - 30, Math.max(30, p.y));
    }
    temperature *= 0.985;
  }
  fitToCanvas(pos, width, height);
  return pos;
}

// Repulsion pushes small graphs against the walls. Centre the drawing and scale it to fit inside
// margins that leave room for the labels drawn under each node.
function fitToCanvas(pos: Map<string, { x: number; y: number }>, width: number, height: number) {
  const mx = 70;
  const top = 30;
  const bottom = 45;
  const ps = [...pos.values()];
  const minX = Math.min(...ps.map((p) => p.x));
  const maxX = Math.max(...ps.map((p) => p.x));
  const minY = Math.min(...ps.map((p) => p.y));
  const maxY = Math.max(...ps.map((p) => p.y));
  const availW = Math.max(1, width - 2 * mx);
  const availH = Math.max(1, height - top - bottom);
  const scale = Math.min(1, availW / Math.max(maxX - minX, 1), availH / Math.max(maxY - minY, 1));
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  for (const p of ps) {
    p.x = mx + availW / 2 + (p.x - cx) * scale;
    p.y = top + availH / 2 + (p.y - cy) * scale;
  }
}
