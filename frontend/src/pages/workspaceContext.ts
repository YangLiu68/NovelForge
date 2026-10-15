import { useOutletContext } from "react-router-dom";

import type { ChapterSummary, Novel } from "../types";

export interface WorkspaceContext {
  novel: Novel;
  chapters: ChapterSummary[];
  refreshChapters: () => Promise<void>;
  refreshNovel: () => Promise<void>;
}

export const useWorkspace = () => useOutletContext<WorkspaceContext>();
