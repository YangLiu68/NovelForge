import assert from "node:assert/strict";
import { test } from "node:test";

import { forceLayout } from "./layout.ts";

test("layout is deterministic and stays inside the canvas", () => {
  const nodes = ["a", "b", "c", "d"].map((id) => ({ id, weight: 1 }));
  const edges = [
    { source: "a", target: "b", weight: 5 },
    { source: "b", target: "c", weight: 1 },
  ];
  const one = forceLayout(nodes, edges, 600, 400);
  const two = forceLayout(nodes, edges, 600, 400);
  assert.deepEqual([...one.entries()], [...two.entries()]);
  for (const { x, y } of one.values()) {
    assert.ok(x >= 40 && x <= 560 && y >= 30 && y <= 370);
  }
});

test("strongly connected nodes end up closer than unconnected ones", () => {
  const nodes = ["a", "b", "c"].map((id) => ({ id, weight: 1 }));
  const p = forceLayout(nodes, [{ source: "a", target: "b", weight: 10 }], 600, 400);
  const d = (u: string, v: string) =>
    Math.hypot(p.get(u)!.x - p.get(v)!.x, p.get(u)!.y - p.get(v)!.y);
  assert.ok(d("a", "b") < d("a", "c"));
});

test("small graphs are centred with room for labels", () => {
  const nodes = ["a", "b", "c"].map((id) => ({ id, weight: 1 }));
  const edges = [
    { source: "a", target: "b", weight: 1 },
    { source: "a", target: "c", weight: 1 },
  ];
  const p = [...forceLayout(nodes, edges, 720, 450).values()];
  const xs = p.map((q) => q.x);
  const ys = p.map((q) => q.y);
  assert.ok(Math.abs((Math.min(...xs) + Math.max(...xs)) / 2 - 360) < 1);
  assert.ok(Math.min(...xs) >= 70 && Math.max(...xs) <= 650);
  assert.ok(Math.min(...ys) >= 30 && Math.max(...ys) <= 405);
});
