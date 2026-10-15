export interface Novel {
  id: string;
  slug: string | null;
  title: string;
  synopsis: string;
  version: number;
  created_at: string;
  updated_at: string;
  chapter_count: number;
  character_count: number;
}

export interface ChapterSummary {
  id: string;
  novel_id: string;
  number: number;
  title: string;
  story_day: number | null;
  story_time_label: string | null;
  version: number;
  updated_at: string;
  word_count: number;
}

export interface Chapter extends ChapterSummary {
  body: string;
  content_hash: string;
}

export interface RevisionSummary {
  id: string;
  version: number;
  title: string;
  content_hash: string;
  created_at: string;
}

export interface Revision extends RevisionSummary {
  body: string;
}

export interface Character {
  id: string;
  novel_id: string;
  name: string;
  aliases: string[];
  description: string;
  attributes: Record<string, string>;
  version: number;
  updated_at: string;
}

export interface SpanRef {
  chapter_id: string;
  chapter_number: number;
  chapter_title: string;
  chapter_version: number;
  start: number;
  end: number;
  quote: string;
}

export interface Claim {
  id: string;
  subject_character_id: string | null;
  subject_name: string;
  predicate: string;
  value: string;
  raw_value: string;
  modality: "asserted" | "hedged" | "reported";
  confidence: number;
  status: string;
  extractor: string;
  effective_day: number | null;
  time_certainty: string;
  evidence: SpanRef[];
}

export interface SearchHit {
  passage_id: string;
  chapter_id: string;
  chapter_number: number;
  chapter_title: string;
  chapter_version: number;
  start: number;
  end: number;
  text: string;
  score: number;
  highlights: [number, number][];
}

export interface SearchResult {
  query: string;
  hits: SearchHit[];
  took_ms: number;
}

export interface Evidence extends SpanRef {
  claim_id: string;
  value: string;
  modality: string;
  confidence: number;
  effective_day: number | null;
  time_certainty: string;
}

export interface Finding {
  id: string;
  kind: "attribute_conflict" | "canon_conflict" | "age_timeline";
  category: string;
  subject_id: string;
  subject_name: string;
  predicate: string;
  severity: "high" | "medium" | "low";
  explanation: string;
  suggestion: string;
  canon_value: string | null;
  evidence: Evidence[];
}

export interface Report {
  novel_id: string;
  min_confidence: number;
  claims_considered: number;
  findings: Finding[];
  took_ms: number;
}
