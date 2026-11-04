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
  length_unit?: "words" | "characters";
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

export type SearchMode = "keyword" | "fts" | "vector" | "hybrid" | "hybrid_rerank";

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
  ranks: Record<string, number>;
}

export interface SearchResult {
  query: string;
  mode: SearchMode;
  embedder: string | null;
  reranker: string | null;
  hits: SearchHit[];
  took_ms: number;
  timings_ms: Record<string, number>;
  index_coverage: { total: number; embedded: number } | null;
}

export interface JobStats {
  counts: Record<string, number>;
}

export interface Evidence extends SpanRef {
  claim_id: string | null;
  value: string;
  modality: string;
  confidence: number;
  effective_day: number | null;
  time_certainty: string;
}

export interface Finding {
  id: string;
  kind:
    | "attribute_conflict"
    | "canon_conflict"
    | "age_timeline"
    | "dead_character_active"
    | "location_conflict"
    | "ability_conflict"
    | "world_rule_violation";
  category: string;
  subject_id: string;
  subject_name: string;
  predicate: string;
  severity: "high" | "medium" | "low";
  explanation: string;
  suggestion: string;
  canon_value: string | null;
  evidence: Evidence[];
  status: "open" | "dismissed" | "resolved" | "preview";
  status_note: string | null;
  detector: string;
  auto_resolved: boolean;
}

export interface Report {
  novel_id: string;
  min_confidence: number;
  claims_considered: number;
  status_counts: Record<string, number>;
  findings: Finding[];
  took_ms: number;
}

export interface ReviewItem {
  id: string;
  subject_character_id: string | null;
  subject_name: string;
  predicate: string;
  value: string;
  modality: string;
  confidence: number;
  status: "proposed" | "accepted" | "rejected";
  extractor: string;
  effective_day: number | null;
  time_certainty: string;
  details: Record<string, unknown>;
  review_note: string | null;
  canon_value: string | null;
  evidence: SpanRef[];
}

export interface ReviewPage {
  total: number;
  counts: Record<string, number>;
  items: ReviewItem[];
}

export interface Canon {
  characters: { id: string; name: string; attributes: Record<string, string> }[];
  locations: { id: string; name: string; travel_days: Record<string, number> }[];
  world_rules: { id: string; statement: string; status: string; chapter_number: number | null }[];
  timeline: {
    id: string;
    kind: string;
    description: string;
    character: string | null;
    location: string | null;
    story_day: number | null;
    chapter_number: number | null;
  }[];
  plot_threads: {
    id: string;
    title: string;
    status: string;
    setup_chapter: number | null;
    payoff_chapter: number | null;
  }[];
  relationships: { id: string; source: string; target: string; kind: string }[];
}

export interface CanonChange {
  id: string;
  entity_type: string;
  field: string;
  old_value: unknown;
  new_value: unknown;
  source_claim_id: string | null;
  actor: string;
  note: string | null;
  created_at: string;
}

export interface CritiqueIssue {
  kind: string;
  category: string;
  severity: string;
  subject: string;
  explanation: string;
  suggestion: string;
  draft_evidence: Evidence[];
  established_evidence: Evidence[];
  canon_value: string | null;
}

export interface Critique {
  issues: CritiqueIssue[];
  draft_facts: number;
  checked_against_facts: number;
  words: number;
  method: string;
}

export interface WorkflowRun {
  id: string;
  novel_id: string;
  chapter_id: string | null;
  base_version: number | null;
  goal: string;
  llm: string;
  status: string;
  iteration: number;
  max_iterations: number;
  plan: string | null;
  draft: string | null;
  critique: Critique | null;
  applied_chapter_id: string | null;
  applied_version: number | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  error: string | null;
  created_at: string;
  steps?: { id: string; kind: string; attempt: number; status: string; chars: number }[];
}

export interface GraphNode {
  id: string;
  name: string;
  mentions: number;
  first_chapter: number | null;
  attributes: Record<string, string>;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  relationships: string[];
  samples: {
    chapter_id: string;
    chapter_number: number;
    chapter_version: number;
    start: number;
    end: number;
    quote: string;
  }[];
}

export interface TimelineEvent {
  claim_id: string;
  day: number;
  chapter_id: string;
  chapter_number: number | null;
  chapter_version: number | null;
  predicate: string;
  family: string;
  value: string;
  status: string;
  start: number | null;
  end: number | null;
  quote: string;
}

export interface TimelineData {
  lanes: { character_id: string; name: string; events: TimelineEvent[] }[];
  findings: {
    id: string;
    kind: string;
    severity: string;
    subject_id: string | null;
    claim_ids: string[];
    explanation: string;
  }[];
  day_range: [number, number] | null;
  chapters: { number: number; story_day: number | null }[];
  undated_claims: number;
}

// Story-logic audit (character motives, plot logic, pacing, revision plan).
export interface StoryNote {
  id: string;
  character: string;
  kind: string;
  text: string;
  chapter: number | null;
  quote: string | null;
  start: number | null;
  end: number | null;
  located: string | null;
}

export interface StoryBeat {
  id: string;
  chapter: number;
  character: string;
  listed: boolean;
  action: string;
  quote: string;
  start: number;
  end: number;
  hostile: boolean;
  target: string;
  cost: string;
  located: string;
  resolves_crisis?: boolean;
  uses_secret?: boolean;
  secret?: string;
}

export interface StorySetup {
  id: string;
  chapter: number;
  text: string;
  quote: string;
  start: number;
  end: number;
  key?: string;
}

export interface StoryPulse {
  chapter: number;
  summary: string;
  tension: number;
  emotions: string[];
  hook: boolean;
  hook_quote: string | null;
  hook_start: number | null;
  hook_end: number | null;
}

export interface StoryJudgement {
  beat: string;
  model_verdict: string;
  verdict: string;
  severity: number;
  reasoning: string;
  motives: { motive: string; support: string[] }[];
  conflicts: { note: string; why: string }[];
  fixes: string[];
  explained_by: string | null;
  explained_why: string | null;
  checks: string[];
}

export interface StoryEvidence {
  chapter: number;
  start: number;
  end: number;
  quote: string;
  role: string;
}

export interface StoryIssue {
  id: string;
  family: "character" | "plot" | "pacing";
  kind: string;
  chapter: number;
  chapters: number[];
  character: string | null;
  severity: number;
  title: string;
  explanation: string;
  evidence: StoryEvidence[];
  refs: string[];
  fixes: string[];
  rationale?: string;
  /** Titles (or kinds) of findings folded into this one: the same scene or the same beat. */
  merged?: string[];
}

export interface StorySuggestion {
  targets: string[];
  chapter: number;
  technique: string;
  change: string;
  why: string;
  sample: string;
}

export interface StoryAuditResult {
  language: "zh" | "en";
  llm: string;
  prompt_version: string;
  chapters: { number: number; title: string }[];
  cast: string[];
  notes: StoryNote[];
  beats: StoryBeat[];
  setups: StorySetup[];
  pulses: StoryPulse[];
  judgements: StoryJudgement[];
  issues: StoryIssue[];
  suggestions: StorySuggestion[];
  rejected: { stage: string; chapter: number | null; reason: string }[];
  errors: string[];
  usage: {
    calls?: number;
    input_tokens?: number;
    output_tokens?: number;
    cost_usd?: number | null;
    llm_seconds?: number;
  };
}

export interface StoryAuditRun {
  id: string;
  novel_id: string;
  llm: string;
  prompt_version: string;
  status: "queued" | "running" | "done" | "failed";
  progress: string | null;
  error: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  created_at: string;
  finished_at: string | null;
  stale_chapters: string[];
  chapter_versions: Record<string, number>;
  chapter_ids: Record<string, string>;
  counts?: { issues: number; severe: number; suggestions: number };
  result?: StoryAuditResult | null;
}
