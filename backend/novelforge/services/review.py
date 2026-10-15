"""Human review of extracted claims: the only path from proposals to canon.

- accept: marks the claim accepted and applies it to canon (character sheet, locations, world
  rules, timeline, plot threads, relationships). If canon already holds a DIFFERENT value, the
  accept is refused with CanonConflict unless the reviewer explicitly asks to replace it.
- reject: marks the claim rejected; rejected claims never feed the contradiction report.
- Every canon change writes a CanonChange row (old value, new value, source claim).
- Decisions are remembered by claim fingerprint and re-applied when the chapter is re-extracted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from novelforge.models import (
    CanonChange,
    Character,
    Claim,
    Location,
    PlotThread,
    Relationship,
    ReviewDecision,
    TimelineEvent,
    WorldRule,
)
from novelforge.services.errors import Conflict

SHEET_ATTRIBUTES = ("eye_color", "hair_color", "handedness", "birthplace")


class CanonConflict(Conflict):
    def __init__(self, message: str, canon_value: Any):
        super().__init__(message)
        self.canon_value = canon_value


def _audit(
    session: Session,
    claim: Claim | None,
    novel_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID | None,
    field: str,
    old: Any,
    new: Any,
    note: str | None = None,
) -> None:
    session.add(
        CanonChange(
            novel_id=novel_id,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            old_value=old,
            new_value=new,
            source_claim_id=claim.id if claim else None,
            note=note,
        )
    )


def _remember(session: Session, claim: Claim, decision: str, note: str | None) -> None:
    session.execute(
        insert(ReviewDecision)
        .values(
            novel_id=claim.novel_id, fingerprint=claim.fingerprint, decision=decision, note=note
        )
        .on_conflict_do_update(
            index_elements=["novel_id", "fingerprint"],
            set_={"decision": decision, "note": note, "decided_at": datetime.now(UTC)},
        )
    )


def canon_value(session: Session, claim: Claim) -> str | None:
    """The current canon value this claim would set, if canon has one."""
    if claim.predicate in SHEET_ATTRIBUTES and claim.subject_character_id:
        character = session.get(Character, claim.subject_character_id)
        return (character.attributes or {}).get(claim.predicate) if character else None
    return None


def accept(
    session: Session,
    claim: Claim,
    replace_canon: bool = False,
    value: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if claim.status == "accepted":
        return {"status": "accepted", "changed": []}
    if value is not None and value.strip() and value.strip() != claim.value:
        _audit(
            session,
            claim,
            claim.novel_id,
            "claim",
            claim.id,
            "value",
            claim.value,
            value.strip(),
            note="edited during review",
        )
        claim.value = value.strip()
    changed: list[str] = []
    p = claim.predicate
    if p in SHEET_ATTRIBUTES:
        if claim.subject_character_id is None:
            raise Conflict("This claim has no character to apply it to.")
        character = session.get(Character, claim.subject_character_id)
        current = (character.attributes or {}).get(p)
        differs = current is not None and current.lower() != claim.value.lower()
        if differs and not replace_canon:
            raise CanonConflict(
                f"{character.name}'s {p.replace('_', ' ')} is '{current}' in canon. "
                f"Accepting would replace it with '{claim.value}'.",
                current,
            )
        if current is None or current.lower() != claim.value.lower():
            character.attributes = {**(character.attributes or {}), p: claim.value}
            _audit(
                session,
                claim,
                claim.novel_id,
                "character",
                character.id,
                f"attributes.{p}",
                current,
                claim.value,
                note,
            )
            changed.append(f"character.{p}")
    elif p == "location":
        loc = session.scalar(
            select(Location).where(
                Location.novel_id == claim.novel_id, Location.name == claim.value
            )
        )
        if loc is None:
            loc = Location(novel_id=claim.novel_id, name=claim.value)
            session.add(loc)
            session.flush()
            _audit(
                session,
                claim,
                claim.novel_id,
                "location",
                loc.id,
                "created",
                None,
                claim.value,
                note,
            )
            changed.append("location")
        changed += _event(
            session,
            claim,
            "travel",
            f"{claim.subject_text} is in {claim.value}",
            location=claim.value,
            note=note,
        )
    elif p == "status" and claim.value == "dead":
        changed += _event(session, claim, "death", f"{claim.subject_text} dies", note=note)
    elif p.startswith("ability:"):
        skill = p.split(":", 1)[1]
        changed += _event(
            session,
            claim,
            f"ability_{claim.value}",
            f"{claim.subject_text}: {claim.value} {skill}",
            note=note,
        )
    elif p == "world_rule":
        rule = WorldRule(
            novel_id=claim.novel_id,
            statement=claim.value,
            source_claim_id=claim.id,
            source_chapter_id=claim.chapter_id,
        )
        session.add(rule)
        session.flush()
        _audit(
            session,
            claim,
            claim.novel_id,
            "world_rule",
            rule.id,
            "created",
            None,
            claim.value,
            note,
        )
        changed.append("world_rule")
    elif p == "foreshadowing":
        thread = PlotThread(
            novel_id=claim.novel_id,
            title=claim.value,
            status="open",
            setup_chapter_id=claim.chapter_id,
            source_claim_id=claim.id,
        )
        session.add(thread)
        session.flush()
        _audit(
            session,
            claim,
            claim.novel_id,
            "plot_thread",
            thread.id,
            "created",
            None,
            claim.value,
            note,
        )
        changed.append("plot_thread")
    elif p == "relationship":
        changed += _relationship(session, claim, note)
    elif p in ("event", "causal"):
        changed += _event(session, claim, p, claim.value, note=note)
    claim.status = "accepted"
    claim.reviewed_at = datetime.now(UTC)
    claim.review_note = note
    _remember(session, claim, "accepted", note)
    return {"status": "accepted", "changed": changed}


def _event(
    session: Session,
    claim: Claim,
    kind: str,
    description: str,
    location: str | None = None,
    note: str | None = None,
) -> list[str]:
    event = TimelineEvent(
        novel_id=claim.novel_id,
        kind=kind,
        description=description,
        subject_character_id=claim.subject_character_id,
        location=location,
        story_day=claim.effective_day,
        chapter_id=claim.chapter_id,
        source_claim_id=claim.id,
    )
    session.add(event)
    session.flush()
    _audit(
        session,
        claim,
        claim.novel_id,
        "timeline_event",
        event.id,
        "created",
        None,
        description,
        note,
    )
    return ["timeline_event"]


def _relationship(session: Session, claim: Claim, note: str | None) -> list[str]:
    other_name = (claim.details or {}).get("object", "")
    other = (
        session.scalar(
            select(Character).where(
                Character.novel_id == claim.novel_id, Character.name.ilike(other_name)
            )
        )
        if other_name
        else None
    )
    if claim.subject_character_id is None or other is None:
        raise Conflict("Relationship needs two known characters; add the character first.")
    exists = session.scalar(
        select(Relationship).where(
            Relationship.novel_id == claim.novel_id,
            Relationship.source_character_id == claim.subject_character_id,
            Relationship.target_character_id == other.id,
            Relationship.kind == claim.value,
        )
    )
    if exists:
        return []
    rel = Relationship(
        novel_id=claim.novel_id,
        source_character_id=claim.subject_character_id,
        target_character_id=other.id,
        kind=claim.value,
        source_claim_id=claim.id,
    )
    session.add(rel)
    session.flush()
    _audit(
        session, claim, claim.novel_id, "relationship", rel.id, "created", None, claim.value, note
    )
    return ["relationship"]


def reject(session: Session, claim: Claim, note: str | None = None) -> dict[str, Any]:
    claim.status = "rejected"
    claim.reviewed_at = datetime.now(UTC)
    claim.review_note = note
    _remember(session, claim, "rejected", note)
    return {"status": "rejected", "changed": []}
