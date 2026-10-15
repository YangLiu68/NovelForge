"""What the planner and drafter see: canon, nearby text and passages retrieved for the goal."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from novelforge.config import get_settings
from novelforge.models import Chapter, Character, Claim, Novel, PlotThread, WorkflowRun, WorldRule
from novelforge.retrieval.embedders import get_embedder
from novelforge.retrieval.search import search


def _tail(text: str, words: int) -> str:
    parts = text.split()
    return ("… " if len(parts) > words else "") + " ".join(parts[-words:])


def build_context(session: Session, run: WorkflowRun) -> str:
    novel = session.get(Novel, run.novel_id)
    target = session.get(Chapter, run.chapter_id) if run.chapter_id else None
    chapters = list(
        session.scalars(
            select(Chapter).where(Chapter.novel_id == run.novel_id).order_by(Chapter.number)
        )
    )
    number = target.number if target else (chapters[-1].number + 1 if chapters else 1)
    previous = next((c for c in reversed(chapters) if c.number < number), None)
    lines = [f"NOVEL: {novel.title}" + (f" — {novel.synopsis}" if novel.synopsis else "")]

    lines.append("\nCHARACTERS:")
    for c in session.scalars(
        select(Character).where(Character.novel_id == run.novel_id).order_by(Character.name)
    ):
        facts = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in (c.attributes or {}).items())
        alias = f" (also: {', '.join(c.aliases)})" if c.aliases else ""
        lines.append(f"- {c.name}{alias}" + (f" — {facts}" if facts else ""))

    rules = [
        r.statement
        for r in session.scalars(
            select(WorldRule).where(
                WorldRule.novel_id == run.novel_id, WorldRule.status == "active"
            )
        )
    ]
    rules += [
        c.value
        for c in session.scalars(
            select(Claim).where(
                Claim.novel_id == run.novel_id,
                Claim.predicate == "world_rule",
                Claim.status == "accepted",
            )
        )
    ]
    if rules:
        lines.append("\nWORLD RULES:")
        lines += [f"- {r}" for r in dict.fromkeys(rules)]

    threads = [
        t.title
        for t in session.scalars(
            select(PlotThread).where(
                PlotThread.novel_id == run.novel_id, PlotThread.status == "open"
            )
        )
    ]
    if threads:
        lines.append("\nOPEN PLOT THREADS:")
        lines += [f"- {t}" for t in threads]

    if previous is not None:
        when = "unknown time" if previous.story_day is None else f"story day {previous.story_day}"
        lines.append(
            f"\nPREVIOUS CHAPTER ({previous.number}, {when}) ENDS:\n{_tail(previous.body, 250)}"
        )

    try:
        hits = search(
            session, run.novel_id, run.goal, "hybrid", 4, get_embedder(get_settings().embedder)
        ).hits
    except Exception:  # noqa: BLE001 - retrieval is context, not a requirement
        hits = []
    if hits:
        lines.append("\nRELEVANT PASSAGES:")
        lines += [f"[chapter {h.chapter_number}] {h.text}" for h in hits]

    when = "" if target is None or target.story_day is None else f" (story day {target.story_day})"
    if target is not None and target.body.strip():
        lines.append(
            f'\nCURRENT TEXT OF CHAPTER {target.number} "{target.title}"{when}:\n'
            f"{' '.join(target.body.split()[:1500])}"
        )
    else:
        lines.append(f"\nTHE NEW CHAPTER IS CHAPTER {number}{when}.")
    lines.append(f"\nGOAL: {run.goal}")
    return "\n".join(lines)
