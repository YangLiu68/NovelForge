"""Persisted contradiction findings: refresh, dismiss, resolve, reopen.

`refresh_findings` recomputes the rule-based findings and reconciles them with the stored ones:
- new fingerprint -> inserted as open
- seen again -> evidence/explanation updated; a dismissed finding stays dismissed
- auto-resolved earlier but detected again -> reopened
- open but no longer detected -> resolved automatically ("no longer detected")
Findings from other detectors (the LLM rule judge) are left alone.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from novelforge.core.contradictions import Finding
from novelforge.models import Location, StoredFinding
from novelforge.services.errors import Conflict
from novelforge.services.report import contradiction_report

RULES_DETECTOR = "rules"


def fingerprint(f: Finding) -> str:
    parts = sorted(
        f"{e.chapter_id}|{' '.join(e.quote.lower().split())}|{e.value.lower()}" for e in f.evidence
    )
    key = "|".join([f.kind, f.subject_id, f.predicate, *parts])
    return hashlib.sha1(key.encode()).hexdigest()


def travel_matrix(session: Session, novel_id: uuid.UUID) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    for loc in session.scalars(select(Location).where(Location.novel_id == novel_id)):
        for other, days in (loc.travel_days or {}).items():
            out[(loc.name, other)] = int(days)
    return out


def refresh_findings(session: Session, novel_id: uuid.UUID, min_confidence: float) -> dict:
    now = datetime.now(UTC)
    findings, claim_count = contradiction_report(
        session, novel_id, min_confidence, travel=travel_matrix(session, novel_id)
    )
    stored = {
        f.fingerprint: f
        for f in session.scalars(
            select(StoredFinding).where(
                StoredFinding.novel_id == novel_id, StoredFinding.detector == RULES_DETECTOR
            )
        )
    }
    seen: set[str] = set()
    stats = {"new": 0, "updated": 0, "reopened": 0, "auto_resolved": 0}
    for f in findings:
        fp = fingerprint(f)
        if fp in seen:
            continue
        seen.add(fp)
        row = stored.get(fp)
        payload = {
            "kind": f.kind,
            "category": f.category,
            "subject_character_id": uuid.UUID(f.subject_id) if f.subject_id else None,
            "subject_name": f.subject_name,
            "predicate": f.predicate,
            "severity": f.severity,
            "explanation": f.explanation,
            "suggestion": f.suggestion,
            "canon_value": f.canon_value,
            "evidence": [asdict(e) for e in f.evidence],
            "last_seen_at": now,
        }
        if row is None:
            session.add(
                StoredFinding(
                    novel_id=novel_id,
                    fingerprint=fp,
                    detector=RULES_DETECTOR,
                    status="open",
                    **payload,
                )
            )
            stats["new"] += 1
            continue
        for k, v in payload.items():
            setattr(row, k, v)
        stats["updated"] += 1
        if row.status == "resolved" and row.auto_resolved:
            row.status, row.auto_resolved, row.status_note = "open", False, None
            row.status_changed_at = now
            stats["reopened"] += 1
    for fp, row in stored.items():
        if fp not in seen and row.status == "open":
            row.status, row.auto_resolved = "resolved", True
            row.status_note = "No longer detected (the text or canon changed)."
            row.status_changed_at = now
            stats["auto_resolved"] += 1
    session.flush()
    return {**stats, "claims_considered": claim_count}


def set_status(session: Session, finding: StoredFinding, status: str, note: str | None) -> None:
    if status not in ("open", "dismissed", "resolved"):
        raise Conflict(f"unknown status {status!r}")
    if status == "dismissed" and not (note or "").strip():
        raise Conflict(
            "Dismissing a finding needs a reason (e.g. 'intentional: unreliable narrator')."
        )
    finding.status = status
    finding.status_note = note
    finding.auto_resolved = False
    finding.status_changed_at = datetime.now(UTC)
