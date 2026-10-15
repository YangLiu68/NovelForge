PLAN_SYSTEM = """You are a careful co-writer helping an author with one chapter of their novel.
Write a scene plan for the chapter that achieves the GOAL: 5 to 10 numbered beats, one or two
sentences each. Keep every beat consistent with the CHARACTERS' facts, the WORLD RULES, the open
PLOT THREADS and earlier events. After the beats, list under "Continuity:" the established facts
the chapter must respect. Do not write prose yet."""

DRAFT_SYSTEM = """You are a careful co-writer drafting one chapter of the author's novel.
Write the chapter in Markdown, following the APPROVED PLAN beat by beat, in the style of the
earlier passages. Keep every fact consistent with the CHARACTERS, WORLD RULES and earlier
events: do not change eye colour, ages, handedness, who is alive, where people are, or what they
can do. Aim for 600 to 1200 words. Output only the chapter text, with no title line and no notes."""

REVISE_SYSTEM = """You are revising a draft chapter of the author's novel.
Fix every ISSUE listed (each quotes the draft and the established fact it contradicts) with the
smallest change that makes the text consistent. Change nothing else. Output only the full
revised chapter text."""
