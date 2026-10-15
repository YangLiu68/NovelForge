# Demo video script (about 6 minutes)

Recording setup: 1440×900 browser window, light theme, the API with real local models
(`EMBEDDER=fastembed RERANKER=cross-encoder`), the sample imported fresh, and a second terminal
for the benchmark command. Keep the cursor slow; pause one beat after every click.

| Time | Screen | Narration |
|---|---|---|
| 0:00 | Home page | "Long novels drift: eye colours change, the dead walk, people cross a country in an afternoon. NovelForge catches that, and it never asks you to trust it: every finding points at the exact words." |
| 0:15 | Click **Import sample** → Overview | "Three original chapters, three characters. Import is deterministic: the same files always produce the same database." |
| 0:30 | **Contradictions** | "Four open findings. Each has a category, an explanation, a suggested fix and the evidence." Hover the severity badges. |
| 0:50 | Click “Mara's eyes were green” | "One click opens the chapter at that exact span. Offsets are tied to the chapter version, so a stale citation is flagged rather than silently wrong." |
| 1:05 | Back → tick **Include hedged statements** | "Two more appear: a perception in fog and a clerk's wrong words in dialogue. By default only the narrator's statements count, so these never become false alarms." Untick. |
| 1:25 | **Dismiss…** on handedness → reason "intentional: Tomas lies" | "Dismissals need a reason and survive edits and re-runs, keyed on the evidence text." Show the Dismissed tab. |
| 1:45 | **Review** | "Extracted facts are proposals. Accept Mara's grey eyes: it goes onto the character sheet and into the change log." Click Accept. |
| 2:00 | Accept “Tomas was born in Hollin” → conflict banner | "Canon says Varrow. NovelForge refuses to overwrite canon silently; I choose." Click **Keep canon**. |
| 2:15 | **Canon** | "Timeline, world rules, plot threads, and an audit log of every change with its source." |
| 2:30 | **Search** → type "How would you describe Mara's gaze?" | "Hybrid search: full-text plus embeddings, fused, then reranked. The chips show why each paragraph ranked: words #3, meaning #1, reranked #1." Switch to Exact to show it finds nothing. |
| 3:00 | **Characters & timeline** → graph | "Who appears with whom, weighted by shared paragraphs; click a pair for the evidence." Click Mara–Tomas. |
| 3:15 | Timeline tab, Story day axis | "Each lane is a character; each dot a dated fact. The red dashed arc is the age contradiction: forty on day 0, forty-six on day 3." Click a dot → chapter opens at the span. |
| 3:40 | Chapter 3 → **Draft with assistant** → goal "Mara returns to the archive" → Start | "The assistant plans first. Nothing touches the manuscript yet." |
| 4:00 | Edit one beat → **Approve plan and draft** | "Approved plans stream into a draft. I can cancel at any time; partial output is never used." |
| 4:20 | Critique panel | "The draft is checked against everything established with the same detectors. Here it gave Mara blue eyes, and it cites chapter 1." (Use a run where the model slips; with the mock, show a clean check.) |
| 4:40 | **Revise (1 left)** → clean check → **Apply** | "Revisions are bounded. Applying is a normal versioned save: if I had edited the chapter meanwhile, it would refuse." Open History. |
| 5:00 | Terminal: `uv run novelforge bench-consistency bench/corpora/syn-100-s7` | "And it is measured. A seeded 100-chapter novel with planted contradictions and look-alike negatives." |
| 5:20 | The results table | "Same extractor, same detectors; only the memory differs. Only the current chapter: about a quarter found. Vector retrieval: a third. The structured claim store: two thirds, with no false alarms on the negatives. The misses are listed and explained in the benchmark write-up." (Read the numbers from BENCHMARK.md for the version you record.) |
| 5:45 | BENCHMARK.md | "Every number here comes from a committed command with a seed. Retrieval, extraction, contradictions and load tests up to a thousand chapters." |
| 6:00 | End card: repository URL | "NovelForge. Evidence first." |

Recording notes
- Before recording, run `bench/run_all.sh` and copy the numbers you will say aloud from
  BENCHMARK.md; do not improvise figures.
- If you show an LLM-written draft, say which model wrote it.
