import type {
  Canon,
  CanonChange,
  Chapter,
  ChapterSummary,
  Character,
  Claim,
  GraphEdge,
  GraphNode,
  JobStats,
  Novel,
  Report,
  ReviewPage,
  Revision,
  RevisionSummary,
  SearchMode,
  SearchResult,
  StoryAuditRun,
  TimelineData,
  WorkflowRun,
} from "./types";

export class ApiError extends Error {
  status: number;
  currentVersion: number | null;

  constructor(status: number, message: string, currentVersion: number | null = null) {
    super(message);
    this.status = status;
    this.currentVersion = currentVersion;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d.msg ?? "invalid input").join("; ")
      : (detail ?? res.statusText);
    throw new ApiError(res.status, String(message), data?.current_version ?? null);
  }
  return data as T;
}

const q = (params: Record<string, string | number | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) s.set(k, String(v));
  return s.toString();
};

export const api = {
  listNovels: () => request<Novel[]>("GET", "/api/novels"),
  createNovel: (title: string, synopsis = "") =>
    request<Novel>("POST", "/api/novels", { title, synopsis }),
  getNovel: (id: string) => request<Novel>("GET", `/api/novels/${id}`),
  updateNovel: (id: string, version: number, fields: Partial<Novel>) =>
    request<Novel>("PATCH", `/api/novels/${id}`, { ...fields, version }),
  deleteNovel: (id: string) => request<void>("DELETE", `/api/novels/${id}`),

  listChapters: (novelId: string) =>
    request<ChapterSummary[]>("GET", `/api/novels/${novelId}/chapters`),
  createChapter: (novelId: string, title: string) =>
    request<Chapter>("POST", `/api/novels/${novelId}/chapters`, { title }),
  getChapter: (id: string) => request<Chapter>("GET", `/api/chapters/${id}`),
  updateChapter: (id: string, version: number, fields: Partial<Chapter>) =>
    request<Chapter>("PATCH", `/api/chapters/${id}`, { ...fields, version }),
  deleteChapter: (id: string) => request<void>("DELETE", `/api/chapters/${id}`),
  listRevisions: (id: string) => request<RevisionSummary[]>("GET", `/api/chapters/${id}/revisions`),
  getRevision: (id: string, version: number) =>
    request<Revision>("GET", `/api/chapters/${id}/revisions/${version}`),

  listCharacters: (novelId: string) =>
    request<Character[]>("GET", `/api/novels/${novelId}/characters`),
  createCharacter: (novelId: string, fields: Partial<Character>) =>
    request<Character>("POST", `/api/novels/${novelId}/characters`, fields),
  updateCharacter: (id: string, version: number, fields: Partial<Character>) =>
    request<Character>("PATCH", `/api/characters/${id}`, { ...fields, version }),
  deleteCharacter: (id: string) => request<void>("DELETE", `/api/characters/${id}`),

  search: (novelId: string, query: string, mode: SearchMode = "hybrid") =>
    request<SearchResult>("GET", `/api/novels/${novelId}/search?${q({ q: query, mode })}`),
  jobs: () => request<JobStats>("GET", "/api/jobs"),
  claims: (novelId: string) => request<Claim[]>("GET", `/api/novels/${novelId}/claims`),
  contradictions: (novelId: string, includeUncertain = false, status = "open") =>
    request<Report>(
      "GET",
      `/api/novels/${novelId}/contradictions?${q({
        include_uncertain: String(includeUncertain),
        status,
      })}`,
    ),
  setFindingStatus: (id: string, action: "dismiss" | "resolve" | "reopen", note?: string) =>
    request<{ status: string }>("POST", `/api/findings/${id}/${action}`, { note }),
  judgeRules: (novelId: string) =>
    request<{ queued: string; rules: number; llm: string }>(
      "POST",
      `/api/novels/${novelId}/judge-rules`,
    ),

  review: (novelId: string, status = "proposed", family?: string, offset = 0) =>
    request<ReviewPage>(
      "GET",
      `/api/novels/${novelId}/review?${q({ status, family, offset, limit: 50 })}`,
    ),
  acceptClaim: (id: string, body: { replace_canon?: boolean; value?: string; note?: string }) =>
    request<{ status: string; changed: string[] }>("POST", `/api/claims/${id}/accept`, body),
  rejectClaim: (id: string, note?: string) =>
    request<{ status: string }>("POST", `/api/claims/${id}/reject`, { note }),
  acceptBatch: (novelId: string, claimIds: string[]) =>
    request<{ accepted: string[]; skipped: { id: string; reason: string }[] }>(
      "POST",
      `/api/novels/${novelId}/review/accept-batch`,
      { claim_ids: claimIds },
    ),
  canon: (novelId: string) => request<Canon>("GET", `/api/novels/${novelId}/canon`),
  canonChanges: (novelId: string) =>
    request<CanonChange[]>("GET", `/api/novels/${novelId}/canon/changes`),
  extract: (novelId: string, llm?: string) =>
    request<{ queued_for: number; llm: string }>(
      "POST",
      `/api/novels/${novelId}/extract?${q({ llm })}`,
    ),
  llmConfig: () =>
    request<{ llm: string; llm_extraction_on_save: boolean; effort: string }>("GET", "/api/llm"),

  startWorkflow: (
    novelId: string,
    body: { goal: string; chapter_id?: string | null; max_iterations?: number },
  ) => request<WorkflowRun>("POST", `/api/novels/${novelId}/workflows`, body),
  listWorkflows: (novelId: string) =>
    request<WorkflowRun[]>("GET", `/api/novels/${novelId}/workflows`),
  getWorkflow: (id: string) => request<WorkflowRun>("GET", `/api/workflows/${id}`),
  startStoryAudit: (novelId: string, llm?: string) =>
    request<StoryAuditRun>("POST", `/api/novels/${novelId}/story-audits`, llm ? { llm } : {}),
  listStoryAudits: (novelId: string) =>
    request<StoryAuditRun[]>("GET", `/api/novels/${novelId}/story-audits`),
  getStoryAudit: (id: string) => request<StoryAuditRun>("GET", `/api/story-audits/${id}`),
  approvePlan: (id: string, plan: string) =>
    request<WorkflowRun>("POST", `/api/workflows/${id}/approve-plan`, { plan }),
  decide: (id: string, action: "apply" | "revise" | "discard", force = false) =>
    request<{ status: string; chapter_id?: string; version?: number; run?: WorkflowRun }>(
      "POST",
      `/api/workflows/${id}/decide`,
      { action, force },
    ),
  cancelWorkflow: (id: string) =>
    request<{ cancelled: boolean }>("POST", `/api/workflows/${id}/cancel`),
  retryWorkflow: (id: string) => request<WorkflowRun>("POST", `/api/workflows/${id}/retry`),

  graph: (novelId: string) =>
    request<{ nodes: GraphNode[]; edges: GraphEdge[] }>("GET", `/api/novels/${novelId}/graph`),
  timeline: (novelId: string) => request<TimelineData>("GET", `/api/novels/${novelId}/timeline`),

  listSamples: () => request<{ name: string }[]>("GET", "/api/samples"),
  importSample: (name: string) =>
    request<{ novel_id: string; created: boolean }>("POST", `/api/samples/${name}/import`),
};
