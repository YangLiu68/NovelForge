# Demo walkthrough (Milestone 1, about five minutes)

Setup: follow the README quick start (API on :8000, UI on :5173). Start from an empty database
(`uv run novelforge migrate base && uv run novelforge migrate`; this deletes everything in the local dev database) so the import is shown live.

1. **Home page.** "NovelForge keeps long manuscripts consistent. Every fact it extracts points back
   to the exact words it came from." Click **Import sample "lanternfall"**. Three original
   chapters and three characters load; the import is deterministic, so clicking again changes
   nothing.

2. **Contradictions.** Open **Contradictions**: four findings.
   - Mara's eyes are grey in chapter 1 and green in chapter 3.
   - Tomas is left-handed in chapter 1 and right-handed three days later.
   - Tomas's birthplace contradicts his character sheet (Varrow vs. Hollin).
   - Ilsa is 40 on day 0 and 46 on day 3; the explanation does the date arithmetic.
   Point out the severity, the explanation, and the suggested correction.

3. **Click a citation.** Click "Mara's eyes were green". The chapter opens with exactly that
   span highlighted. "Offsets are stored against a specific chapter version; if the chapter has
   changed since, the page says so."

4. **What it does not flag.** Tick **Include hedged statements and dialogue**: two more findings
   appear. "In the fog, Ilsa's eyes seemed almost black" is a perception, and the clerk's "blue
   eyes" is a character's (wrong) words in dialogue. By default these stay out of the report.
   Then mention the case it misses: chapter 3 changes Mara's hair colour, but only through "Her
   hair, cropped short since the year of the fever, had gone the red of rust". The rule extractor
   follows "her" back to a name only in its fixed phrasings ("her red hair", "Her hair was red"),
   and this is not one of them. That gap is labelled in the ground truth and is what the LLM
   extractor has to close.

5. **Fix it in the editor.** Switch to **Write**, change "green" to "grey", save. Back on
   **Contradictions** there are three findings. Open **History** on the chapter to show both
   versions.

6. **Conflict handling.** Open the same chapter in a second tab, save there, then save in the
   first tab: "Not saved", with a choice to load the latest or save on top (the overwritten version
   stays in history).

7. **Search.** Search `marsh`: stemmed matches ("Marshes") are highlighted, and each result opens
   the passage in context.

8. **Close.** Run `uv run novelforge eval-sample` in a terminal to show the scored result against
   the labelled ground truth, and be explicit that this is a three-chapter smoke check, not a
   benchmark. Next milestones: hybrid retrieval with measured recall@k, LLM extraction with human
   review, and a seeded benchmark at 100 and 1,000 chapters.
