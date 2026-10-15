// The API reports offsets in Unicode code points (Python string indices). JavaScript strings
// index UTF-16 code units, which differ whenever the text contains characters outside the
// Basic Multilingual Plane (emoji, some CJK). These helpers convert between the two.

/** UTF-16 index of the given code-point offset (clamped to the string). */
export function cpToUtf16(text: string, cp: number): number {
  if (cp <= 0) return 0;
  let units = 0;
  let points = 0;
  while (units < text.length && points < cp) {
    const code = text.charCodeAt(units);
    units += code >= 0xd800 && code <= 0xdbff && units + 1 < text.length ? 2 : 1;
    points += 1;
  }
  return units;
}

/** text[start:end] with code-point offsets, like Python slicing. */
export function sliceCp(text: string, start: number, end: number): string {
  return text.slice(cpToUtf16(text, start), cpToUtf16(text, end));
}

export interface Segment {
  text: string;
  marked: boolean;
}

/** Split `text` into plain and marked segments. Ranges are code-point offsets relative to text. */
export function segments(text: string, ranges: [number, number][]): Segment[] {
  const sorted = [...ranges].filter(([s, e]) => e > s).sort((a, b) => a[0] - b[0]);
  const out: Segment[] = [];
  let pos = 0;
  for (const [s, e] of sorted) {
    const a = cpToUtf16(text, Math.max(s, 0));
    const b = cpToUtf16(text, e);
    if (a < pos) continue; // overlapping range; keep the earlier one
    if (a > pos) out.push({ text: text.slice(pos, a), marked: false });
    out.push({ text: text.slice(a, b), marked: true });
    pos = b;
  }
  if (pos < text.length) out.push({ text: text.slice(pos), marked: false });
  return out;
}

export interface SpanTarget {
  start: number;
  end: number;
  version: number | null;
}

export function spanHref(
  novelId: string,
  chapterId: string,
  start: number,
  end: number,
  version?: number,
): string {
  const params = new URLSearchParams({ start: String(start), end: String(end) });
  if (version !== undefined) params.set("v", String(version));
  return `/novels/${novelId}/chapters/${chapterId}?${params.toString()}`;
}

export function parseSpan(params: URLSearchParams): SpanTarget | null {
  const start = Number(params.get("start"));
  const end = Number(params.get("end"));
  if (!params.has("start") || !params.has("end") || !Number.isInteger(start)) return null;
  if (!Number.isInteger(end) || end <= start || start < 0) return null;
  const v = params.get("v");
  return { start, end, version: v === null ? null : Number(v) };
}
