"""World-rule violations: retrieval finds candidate passages, an LLM judges them.

For each world rule (canon rules plus proposed, non-rejected world_rule claims), hybrid search
over the novel returns the passages most related to the rule; the passage that states the rule
is excluded. The LLM sees the rule and the numbered candidates and returns the ones whose
narration says the forbidden thing actually happened, each with an exact quote. Quotes are
verified against the passage text; unverifiable answers are dropped.

Findings are stored with detector "rule-judge:<llm>", fingerprinted like rule-based findings so
dismissals persist. This is the one detector that needs an LLM; with the offline mock it finds
nothing (the mock has no judge), which the benchmark reports as such.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from novelforge.config import get_settings
from novelforge.extraction.verify import locate
from novelforge.jobs import enqueue, handler
from novelforge.llm.base import LLM, LLMError
from novelforge.llm.registry import get_llm
from novelforge.models import Chapter, Claim, EvidenceSpan, Novel, StoredFinding, WorldRule
from novelforge.retrieval.embedders import get_embedder
from novelforge.retrieval.search import search

# A sentence that says the act was tried and failed confirms the rule ("tried to cut the
# saltglass, but the knife skidded off"). The prompt says so; a small model still flags some, so
# the code drops them, as it drops quotes it cannot find.
_FAILED_ATTEMPT = re.compile(
    r"\b(?:tried|tries|attempted|attempts|struggled) to\b[^.!?]*?"
    r"\b(?:but|yet|only to|failed|in vain)\b"
    r"|\bfailed to\b|\bin vain\b"
    r"|(?:试图|想要|企图|试着)[^。！？]*?(?:却|但|可是|没能|未能|失败|徒劳)|没能|未能|徒劳",
    re.I,
)


SCHEMA = {
    "title": "rule_judgement",
    "type": "object",
    "additionalProperties": False,
    "required": ["violations"],
    "properties": {
        "violations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["passage", "quote", "explanation", "confidence"],
                "properties": {
                    "passage": {"type": "integer"},
                    "quote": {"type": "string"},
                    "explanation": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        }
    },
}

SYSTEM = """You check a novel for violations of its own world rules.

You get one RULE and numbered PASSAGES from the novel. A passage violates the rule only if the
narration states that the forbidden thing actually happened. These are NOT violations:
attempts that fail, characters knowing, believing or discussing the rule, dialogue, rumours,
dreams, and anything hypothetical.

For each violating passage return its number, an exact quote (copied character for character,
3 to 40 words) of the sentence that breaks the rule, a one-sentence explanation, and your
confidence from 0 to 1. Return {"violations": []} if no passage breaks the rule."""


def collect_rules(session: Session, novel_id: uuid.UUID) -> list[dict[str, Any]]:
    """Canon rules plus proposed (not rejected) world_rule claims, de-duplicated by text."""
    rules: dict[str, dict[str, Any]] = {}
    for r in session.scalars(
        select(WorldRule).where(WorldRule.novel_id == novel_id, WorldRule.status == "active")
    ):
        rules.setdefault(
            " ".join(r.statement.lower().split()),
            {"statement": r.statement, "source_claim_id": r.source_claim_id},
        )
    for c in session.scalars(
        select(Claim).where(
            Claim.novel_id == novel_id, Claim.predicate == "world_rule", Claim.status != "rejected"
        )
    ):
        rules.setdefault(
            " ".join(c.value.lower().split()), {"statement": c.value, "source_claim_id": c.id}
        )
    return list(rules.values())


def judge_rule(
    session: Session, novel_id: uuid.UUID, rule: dict[str, Any], llm: LLM, k: int = 8
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    embedder = get_embedder(get_settings().embedder)
    source = None
    if rule.get("source_claim_id"):
        span = session.scalar(
            select(EvidenceSpan).where(EvidenceSpan.claim_id == rule["source_claim_id"])
        )
        source = span
    hits = search(session, novel_id, rule["statement"], "hybrid", k + 1, embedder).hits
    if source is not None:
        hits = [
            h
            for h in hits
            if not (h.chapter_id == str(source.chapter_id) and h.start <= source.start < h.end)
        ]
    hits = hits[:k]
    if not hits:
        return [], {"candidates": 0}
    passages = "\n\n".join(
        f"[{i}] (chapter {h.chapter_number})\n{h.text}" for i, h in enumerate(hits, start=1)
    )
    prompt = f"RULE: {rule['statement']}\n\nPASSAGES:\n{passages}"
    try:
        result = llm.generate_json(SYSTEM, prompt, SCHEMA, max_tokens=4000)
    except LLMError as exc:
        if exc.kind in ("transport", "config"):
            raise
        return [], {"candidates": len(hits), "error": str(exc)}
    out = []
    dropped = 0
    data = result.data if isinstance(result.data, dict) else {}
    for v in data.get("violations") or []:
        try:
            idx = int(v.get("passage", 0))
        except (TypeError, ValueError):
            continue
        if not 1 <= idx <= len(hits):
            continue
        hit = hits[idx - 1]
        found = locate(hit.text, str(v.get("quote", "")))
        if found is None:
            continue
        if _FAILED_ATTEMPT.search(hit.text[found.start : found.end]):
            dropped += 1
            continue
        start, end = hit.start + found.start, hit.start + found.end
        evidence = []
        if source is not None:
            src_chapter = session.get(Chapter, source.chapter_id)
            evidence.append(
                _evidence(src_chapter, source.start, source.end, source.quote, "rule statement")
            )
        evidence.append(_evidence_from_hit(hit, start, end, hit.text[found.start : found.end]))
        try:
            confidence = max(0.0, min(1.0, float(v.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        out.append(
            {
                "rule": rule["statement"],
                "explanation": str(v.get("explanation", "")).strip()[:1000],
                "confidence": confidence,
                "evidence": evidence,
            }
        )
    usage = {
        "candidates": len(hits),
        "dropped_failed_attempts": dropped,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
    }
    return out, usage


def _evidence(chapter: Chapter, start: int, end: int, quote: str, value: str) -> dict[str, Any]:
    return {
        "claim_id": None,
        "chapter_id": str(chapter.id),
        "chapter_number": chapter.number,
        "chapter_title": chapter.title,
        "chapter_version": chapter.version,
        "start": start,
        "end": end,
        "quote": quote,
        "value": value,
        "modality": "asserted",
        "confidence": 1.0,
        "effective_day": chapter.story_day,
        "time_certainty": "unknown" if chapter.story_day is None else "chapter_day",
    }


def _evidence_from_hit(hit, start: int, end: int, quote: str) -> dict[str, Any]:
    return {
        "claim_id": None,
        "chapter_id": hit.chapter_id,
        "chapter_number": hit.chapter_number,
        "chapter_title": hit.chapter_title,
        "chapter_version": hit.chapter_version,
        "start": start,
        "end": end,
        "quote": quote,
        "value": "violation",
        "modality": "asserted",
        "confidence": 1.0,
        "effective_day": None,
        "time_certainty": "unknown",
    }


def store_violations(
    session: Session, novel_id: uuid.UUID, detector: str, violations: list[dict[str, Any]]
) -> int:
    now = datetime.now(UTC)
    new = 0
    for v in violations:
        parts = sorted(
            f"{e['chapter_id']}|{' '.join(e['quote'].lower().split())}" for e in v["evidence"]
        )
        fp = hashlib.sha1(
            "|".join(["world_rule_violation", v["rule"].lower(), *parts]).encode()
        ).hexdigest()
        row = session.scalar(
            select(StoredFinding).where(
                StoredFinding.novel_id == novel_id, StoredFinding.fingerprint == fp
            )
        )
        violation = v["evidence"][-1]
        payload = {
            "detector": detector,
            "kind": "world_rule_violation",
            "category": "world_rules",
            "subject_character_id": None,
            "subject_name": "World rule",
            "predicate": "world_rule",
            "severity": "high" if v["confidence"] >= 0.8 else "medium",
            "explanation": f"Rule: “{v['rule']}”. Chapter {violation['chapter_number']}: "
            f"{v['explanation']}",
            "suggestion": (
                f"Rewrite the chapter {violation['chapter_number']} passage so the rule holds "
                f"(e.g. make it a failed attempt), or retire or amend the rule on the Canon page."
            ),
            "canon_value": v["rule"],
            "evidence": v["evidence"],
            "last_seen_at": now,
        }
        if row is None:
            session.add(StoredFinding(novel_id=novel_id, fingerprint=fp, status="open", **payload))
            new += 1
        else:
            for key, value in payload.items():
                setattr(row, key, value)
    return new


def judge_novel(session: Session, novel_id: uuid.UUID, llm: LLM) -> dict[str, Any]:
    totals: dict[str, Any] = {
        "rules": 0,
        "violations": 0,
        "new": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "errors": [],
    }
    for rule in collect_rules(session, novel_id):
        totals["rules"] += 1
        violations, usage = judge_rule(session, novel_id, rule, llm)
        totals["violations"] += len(violations)
        totals["new"] += store_violations(session, novel_id, f"rule-judge:{llm.name}", violations)
        totals["input_tokens"] += usage.get("input_tokens", 0)
        totals["output_tokens"] += usage.get("output_tokens", 0)
        if totals["cost_usd"] is not None:
            c = usage.get("cost_usd", 0.0)
            totals["cost_usd"] = None if c is None else totals["cost_usd"] + c
        if usage.get("error"):
            totals["errors"].append(usage["error"])
    return totals


def enqueue_judge(session: Session, novel: Novel, llm_spec: str) -> str:
    versions = sorted(
        f"{c.id}:{c.version}"
        for c in session.scalars(select(Chapter).where(Chapter.novel_id == novel.id))
    )
    rules = sorted(r["statement"] for r in collect_rules(session, novel.id))
    digest = hashlib.sha1("|".join(versions + rules).encode()).hexdigest()[:16]
    key = f"judge:{novel.id}:{llm_spec}:{digest}"
    enqueue(session, "judge_rules", key, {"novel_id": str(novel.id), "llm": llm_spec})
    return key


@handler("judge_rules")
def judge_rules_job(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    return judge_novel(session, uuid.UUID(payload["novel_id"]), get_llm(payload["llm"]))
