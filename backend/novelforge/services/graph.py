"""Data for the interactive character graph and timeline.

Graph: characters are nodes (sized by how many paragraphs mention them); an edge joins two
characters who are mentioned in the same paragraph, weighted by how often, with a few example
paragraphs as evidence, plus any accepted relationship kinds.
Timeline: every non-rejected asserted claim with a known story day, grouped per character, and
the open findings that connect them.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from novelforge.core.extraction import surface_forms, who_pattern
from novelforge.models import (
    Chapter,
    Character,
    Claim,
    Passage,
    Relationship,
    StoredFinding,
)
from novelforge.services.derived import character_refs

MAX_SAMPLES = 3


def character_graph(session: Session, novel_id: uuid.UUID) -> dict[str, Any]:
    cast = character_refs(session, novel_id)
    forms = surface_forms(cast)
    chapters = {
        c.id: c for c in session.scalars(select(Chapter).where(Chapter.novel_id == novel_id))
    }
    mentions: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    samples: dict[tuple[str, str], list[dict]] = defaultdict(list)
    first_seen: dict[str, int] = {}
    if forms:
        pattern = re.compile(who_pattern(forms))
        lookup = {f.text.lower(): f.character.id for f in forms}
        rows = session.execute(
            select(Passage.id, Passage.chapter_id, Passage.start, Passage.end, Passage.text).where(
                Passage.novel_id == novel_id
            )
        ).all()
        for row in rows:
            present = sorted({lookup[m.group("who").lower()] for m in pattern.finditer(row.text)})
            ch = chapters.get(row.chapter_id)
            for cid in present:
                mentions[cid] += 1
                if ch is not None:
                    first_seen[cid] = min(first_seen.get(cid, ch.number), ch.number)
            for a, b in combinations(present, 2):
                pairs[(a, b)] += 1
                if len(samples[(a, b)]) < MAX_SAMPLES and ch is not None:
                    samples[(a, b)].append(
                        {
                            "chapter_id": str(row.chapter_id),
                            "chapter_number": ch.number,
                            "chapter_version": ch.version,
                            "start": row.start,
                            "end": row.end,
                            "quote": row.text[:220],
                        }
                    )
    kinds: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in session.scalars(select(Relationship).where(Relationship.novel_id == novel_id)):
        a, b = sorted((str(r.source_character_id), str(r.target_character_id)))
        kinds[(a, b)].append(r.kind)
    chars = {
        str(c.id): c
        for c in session.scalars(select(Character).where(Character.novel_id == novel_id))
    }
    nodes = [
        {
            "id": cid,
            "name": c.name,
            "mentions": mentions.get(cid, 0),
            "first_chapter": first_seen.get(cid),
            "attributes": c.attributes or {},
        }
        for cid, c in chars.items()
    ]
    edges = [
        {
            "source": a,
            "target": b,
            "weight": pairs.get((a, b), 0),
            "relationships": kinds.get((a, b), []),
            "samples": samples.get((a, b), []),
        }
        for a, b in sorted(set(pairs) | set(kinds))
    ]
    return {"nodes": nodes, "edges": edges}


FAMILY = {
    "eye_color": "attribute",
    "hair_color": "attribute",
    "handedness": "attribute",
    "birthplace": "attribute",
    "age": "age",
    "location": "location",
    "status": "status",
}


def timeline(session: Session, novel_id: uuid.UUID) -> dict[str, Any]:
    chapters = {
        c.id: c for c in session.scalars(select(Chapter).where(Chapter.novel_id == novel_id))
    }
    names = {
        c.id: c.name
        for c in session.scalars(select(Character).where(Character.novel_id == novel_id))
    }
    lanes: dict[str, list[dict]] = defaultdict(list)
    undated = 0
    for c in session.scalars(
        select(Claim)
        .where(
            Claim.novel_id == novel_id,
            Claim.status != "rejected",
            Claim.modality == "asserted",
            Claim.subject_character_id.is_not(None),
        )
        .options(selectinload(Claim.evidence))
    ):
        if c.effective_day is None:
            undated += 1
            continue
        ch = chapters.get(c.chapter_id)
        span = c.evidence[0] if c.evidence else None
        lanes[str(c.subject_character_id)].append(
            {
                "claim_id": str(c.id),
                "day": c.effective_day,
                "chapter_id": str(c.chapter_id),
                "chapter_number": ch.number if ch else None,
                "chapter_version": ch.version if ch else None,
                "predicate": c.predicate,
                "family": FAMILY.get(
                    c.predicate, "ability" if c.predicate.startswith("ability:") else "other"
                ),
                "value": c.value,
                "status": c.status,
                "start": span.start if span else None,
                "end": span.end if span else None,
                "quote": span.quote if span else "",
            }
        )
    findings = []
    for f in session.scalars(
        select(StoredFinding).where(
            StoredFinding.novel_id == novel_id, StoredFinding.status == "open"
        )
    ):
        ids = [e["claim_id"] for e in f.evidence if e.get("claim_id")]
        if ids:
            findings.append(
                {
                    "id": str(f.id),
                    "kind": f.kind,
                    "severity": f.severity,
                    "subject_id": str(f.subject_character_id) if f.subject_character_id else None,
                    "claim_ids": ids,
                    "explanation": f.explanation,
                }
            )
    days = [e["day"] for events in lanes.values() for e in events]
    return {
        "lanes": [
            {
                "character_id": cid,
                "name": names.get(uuid.UUID(cid), "?"),
                "events": sorted(events, key=lambda e: (e["day"], e["chapter_number"] or 0)),
            }
            for cid, events in sorted(lanes.items(), key=lambda kv: -len(kv[1]))
        ],
        "findings": findings,
        "day_range": [min(days), max(days)] if days else None,
        "chapters": sorted(
            ({"number": c.number, "story_day": c.story_day} for c in chapters.values()),
            key=lambda c: c["number"],
        ),
        "undated_claims": undated,
    }
