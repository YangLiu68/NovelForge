"""Evidence-grounded critic: check a draft against everything already established.

The draft is treated as a replacement for its target chapter: claims are extracted from it with
the rule extractor and checked, with the same detectors as the contradiction report, against the
claims of every other chapter, the character sheets and travel times. Only findings that involve
the draft are reported, each with the draft quote (offsets into the draft) and the evidence it
contradicts.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novelforge.core.contradictions import detect_contradictions
from novelforge.core.domain import ChapterRef
from novelforge.core.extraction import extract_claims, extractor_for
from novelforge.core.lang import text_length
from novelforge.models import Chapter, WorkflowRun
from novelforge.services.derived import chapter_ref, character_refs
from novelforge.services.findings import travel_matrix
from novelforge.services.report import load_claims, to_extracted

DRAFT_ID = "draft"


def critique(session: Session, run: WorkflowRun, draft: str) -> dict[str, Any]:
    target = session.get(Chapter, run.chapter_id) if run.chapter_id else None
    chapters = [
        chapter_ref(c)
        for c in session.scalars(select(Chapter).where(Chapter.novel_id == run.novel_id))
        if target is None or c.id != target.id
    ]
    if target is not None:
        number, day = target.number, target.story_day
    else:
        number = (
            session.scalar(select(func.max(Chapter.number)).where(Chapter.novel_id == run.novel_id))
            or 0
        ) + 1
        day = max((c.story_day for c in chapters if c.story_day is not None), default=None)
    draft_ref = ChapterRef(DRAFT_ID, number, "Draft", draft, 0, day)
    cast = character_refs(session, run.novel_id)
    draft_claims = extract_claims(draft_ref, cast)
    others = [
        to_extracted(c)
        for c in load_claims(session, run.novel_id)
        if target is None or c.chapter_id != target.id
    ]
    findings = detect_contradictions(
        others + draft_claims,
        [*chapters, draft_ref],
        cast,
        travel=travel_matrix(session, run.novel_id),
    )
    issues = []
    for f in findings:
        if not any(e.chapter_id == DRAFT_ID for e in f.evidence):
            continue
        issues.append(
            {
                "kind": f.kind,
                "category": f.category,
                "severity": f.severity,
                "subject": f.subject_name,
                "explanation": f.explanation.replace(f"chapter {number}", "the draft").replace(
                    f"第 {number} 章", "草稿"
                ),
                "suggestion": f.suggestion,
                "draft_evidence": [asdict(e) for e in f.evidence if e.chapter_id == DRAFT_ID],
                "established_evidence": [asdict(e) for e in f.evidence if e.chapter_id != DRAFT_ID],
                "canon_value": f.canon_value,
            }
        )
    return {
        "issues": issues,
        "draft_facts": len(draft_claims),
        "checked_against_facts": len(others),
        "words": len(draft.split()),
        "length": dict(zip(("count", "unit"), text_length(draft), strict=True)),
        "method": f"{extractor_for(draft)} extraction + NovelForge contradiction detectors",
    }


def issues_for_prompt(critique_: dict[str, Any]) -> str:
    lines = []
    for i, issue in enumerate(critique_.get("issues", []), start=1):
        draft_q = "; ".join(f"“{e['quote']}”" for e in issue["draft_evidence"])
        est = "; ".join(
            f"chapter {e['chapter_number']}: “{e['quote']}”" for e in issue["established_evidence"]
        )
        canon = f" Character sheet: {issue['canon_value']}." if issue.get("canon_value") else ""
        lines.append(
            f"{i}. Draft says {draft_q}. Established: {est or '(character sheet)'}."
            f"{canon} {issue['explanation']}"
        )
    return "\n".join(lines)
