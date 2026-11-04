"""LLM extraction as idempotent background jobs.

Job key: extract:<chapter>:<version>:<llm>:<prompt version>. Re-running for an unchanged chapter,
model and prompt is a no-op; a new chapter version, model or prompt gets a new job. Results
replace only that extractor's claims for the chapter, and earlier review decisions are re-applied
by fingerprint.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from novelforge.extraction.prompt import PROMPT_VERSION, system_for
from novelforge.extraction.runner import extract_with_llm
from novelforge.jobs import SkipJob, enqueue, handler
from novelforge.llm.registry import get_llm
from novelforge.models import Chapter
from novelforge.services.derived import chapter_ref, character_refs, persist_claims


def extraction_key(chapter: Chapter, llm_spec: str) -> str:
    version = system_for(chapter.body)[1] if chapter.body else PROMPT_VERSION
    return f"extract:{chapter.id}:{chapter.version}:{llm_spec}:{version}"


def enqueue_llm_extraction(session: Session, chapter: Chapter, llm_spec: str) -> None:
    enqueue(
        session,
        "extract_chapter",
        extraction_key(chapter, llm_spec),
        {"chapter_id": str(chapter.id), "version": chapter.version, "llm": llm_spec},
        max_attempts=4,
    )


def max_words_for(llm_spec: str) -> int:
    """Words per LLM extraction window. Small local models get small windows (short, bounded
    JSON); hosted models read up to a long chapter at once unless LLM_WINDOW_WORDS says
    otherwise. A replay must cut the same windows as the run it replays."""
    from novelforge.config import get_settings

    if get_settings().llm_window_words > 0:
        return get_settings().llm_window_words
    hosted = llm_spec.removeprefix("replay:").startswith(("anthropic", "openrouter"))
    return 6000 if hosted else 500


@handler("extract_chapter")
def extract_chapter_job(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    chapter = session.get(Chapter, uuid.UUID(payload["chapter_id"]))
    if chapter is None:
        raise SkipJob("chapter deleted")
    if chapter.version != payload["version"]:
        raise SkipJob(f"chapter is at version {chapter.version}, job was for {payload['version']}")
    llm = get_llm(payload["llm"])
    run = extract_with_llm(
        chapter_ref(chapter),
        character_refs(session, chapter.novel_id),
        llm,
        max_words=max_words_for(payload["llm"]),
    )
    stats = persist_claims(session, chapter, run.claims, run.extractor)
    return {**run.summary(), **stats, "rejected_examples": run.rejected[:5]}
