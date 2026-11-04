"""Run an LLM over a chapter and turn its answer into verified claims.

Long chapters are split into windows of whole paragraphs (`max_words`), so a small local model
with an 8k context works as well as Claude. Every returned fact is validated against the schema,
its subject resolved to a known character, and its quote located in the chapter text; anything
that fails is kept in `rejected` with the reason instead of being stored.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from novelforge.core.domain import ChapterRef, CharacterRef, ExtractedClaim, Span
from novelforge.core.extraction import CLAIM_NAMESPACE, surface_forms
from novelforge.core.lang import is_chinese
from novelforge.core.text import number_to_words, split_passages
from novelforge.extraction.prompt import PROMPT_VERSION, system_for, user_prompt
from novelforge.extraction.schema import (
    KINDS_ZH,
    MODALITIES,
    SCHEMA,
    SCHEMA_ZH,
    SUBJECTLESS,
    to_predicate,
)
from novelforge.extraction.verify import locate
from novelforge.llm.base import LLM, LLMError


@dataclass
class ExtractionRun:
    extractor: str
    claims: list[ExtractedClaim] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = 0.0
    latency_ms: float = 0.0
    prompt_version: str = PROMPT_VERSION

    def summary(self) -> dict[str, Any]:
        reasons: dict[str, int] = {}
        for r in self.rejected:
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
        return {
            "extractor": self.extractor,
            "prompt_version": self.prompt_version,
            "claims": len(self.claims),
            "rejected": len(self.rejected),
            "rejected_by_reason": reasons,
            "errors": self.errors,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "latency_ms": round(self.latency_ms, 1),
        }


def windows(body: str, max_words: int) -> list[tuple[int, int]]:
    """Consecutive paragraph groups of at most ~max_words words, as body offsets. Chinese text
    has no spaces; two characters count as a word."""
    out: list[tuple[int, int]] = []
    start = end = None
    words = 0
    zh = is_chinese(body)
    for p in split_passages(body):
        n = len(p.text) // 2 if zh else len(p.text.split())
        if start is not None and words + n > max_words:
            out.append((start, end))
            start, words = None, 0
        if start is None:
            start = p.start
        end = p.end
        words += n
    if start is not None:
        out.append((start, end))
    return out or [(0, len(body))]


# A hair colour whose quote dyes the hair, or that the model marks as a change the text explains
# (object "change"), starts a new period as the rule extractors mark it: the colour before it is
# not contradicted.
_DYE = re.compile(r"(?:染|漂)(?:成|了|得)|\b(?:dyed|coloured|colored|bleached)\b", re.I)

# Kinds whose value is a literal that the quote must contain (value grounding).
GROUNDED = {"eye_color", "hair_color", "handedness", "birthplace", "location", "age"}


def value_grounded(predicate: str, value: str, quote: str, raw: str = "") -> bool:
    """Does the quote actually state this value? A real quote with an unrelated value ("Jorin
    could not swim" offered as evidence that Jorin is at the harbour) is rejected.

    Strict by design: an inferred value ("eyes the colour of sea glass" -> green) is rejected too,
    trading some recall for precision.
    """
    if predicate not in GROUNDED:
        return True
    if is_chinese(quote):
        return _grounded_zh(predicate, value, quote, raw)
    q = quote.lower().replace("-", " ")
    if predicate == "age":
        n = int(value)
        return str(n) in q or number_to_words(n).replace("-", " ") in q
    if predicate == "handedness":
        return value in q
    if predicate in ("eye_color", "hair_color"):
        return value in q or {"grey": "gray", "blond": "blonde"}.get(value, value) in q
    return value.lower().replace("-", " ") in q


def _grounded_zh(predicate: str, value: str, quote: str, raw: str) -> bool:
    from novelforge.core.extraction_zh import CN_NUM, parse_cn_number

    if predicate == "age":
        return any(
            (int(m) if m.isdigit() else parse_cn_number(m)) == int(value)
            for m in re.findall(CN_NUM, quote)
        )
    if predicate == "handedness":
        return {"left": "左", "right": "右"}[value] in quote
    if predicate in ("eye_color", "hair_color"):
        # The colour word as the model copied it (琥珀色 -> 琥珀) must be in the quote.
        word = raw.strip().removesuffix("色")
        return bool(word) and word in quote
    return value in quote


def extract_with_llm(
    chapter: ChapterRef,
    characters: list[CharacterRef],
    llm: LLM,
    max_words: int = 1500,
    check_values: bool = True,
) -> ExtractionRun:
    system, version = system_for(chapter.body)
    zh = is_chinese(chapter.body)
    run = ExtractionRun(extractor=f"llm:{llm.name}", prompt_version=version)
    lookup = {f.text.lower(): f.character for f in surface_forms(characters)}
    if zh:
        from novelforge.core.extraction_zh import surface_forms_zh

        lookup.update({form: c for form, c in surface_forms_zh(characters).items()})
    seen: set[tuple[str, int, int, str]] = set()
    parts = windows(chapter.body, max_words)
    started = time.perf_counter()
    for i, (ws, we) in enumerate(parts, start=1):
        prompt = user_prompt(chapter, characters, chapter.body[ws:we], (i, len(parts)))
        run.calls += 1
        try:
            result = llm.generate_json(system, prompt, SCHEMA_ZH if zh else SCHEMA, max_tokens=8000)
        except LLMError as exc:
            if exc.kind in ("transport", "config"):
                raise  # retried by the job queue
            run.errors.append(f"window {i}: {exc}")
            continue
        run.input_tokens += result.input_tokens
        run.output_tokens += result.output_tokens
        if run.cost_usd is not None:
            run.cost_usd = None if result.cost_usd is None else run.cost_usd + result.cost_usd
        facts = result.data.get("facts") if isinstance(result.data, dict) else None
        if not isinstance(facts, list):
            run.errors.append(f"window {i}: response has no 'facts' list")
            continue
        for fact in facts:
            claim, reason = _to_claim(chapter, fact, lookup, run.extractor, (ws, we), zh)
            if (
                claim is not None
                and check_values
                and not value_grounded(
                    claim.predicate, claim.value, claim.spans[0].quote, claim.raw_value
                )
            ):
                claim, reason = None, "value not in quote"
            if claim is None:
                run.rejected.append({"fact": fact, "reason": reason})
                continue
            key = (
                claim.subject_id or claim.subject_text,
                claim.predicate,
                claim.spans[0].start,
                claim.spans[0].end,
                claim.value,
            )
            if key in seen:
                continue
            seen.add(key)
            run.claims.append(claim)
    run.latency_ms = (time.perf_counter() - started) * 1000
    run.claims.sort(key=lambda c: (c.spans[0].start, c.predicate))
    return run


def _to_claim(
    chapter, fact, lookup, extractor, window, zh=False
) -> tuple[ExtractedClaim | None, str]:
    if not isinstance(fact, dict):
        return None, "not an object"
    kind = fact.get("kind")
    if kind not in KINDS_ZH or (kind == "presence" and not zh):
        return None, "unknown kind"
    modality = fact.get("modality") if fact.get("modality") in MODALITIES else "asserted"
    subject_text = str(fact.get("subject", "")).strip()
    character = lookup.get(subject_text.lower())
    if character is None and subject_text.lower() not in ("world", ""):
        # "Mara Venn's" or a stray title: try the first two words.
        character = lookup.get(" ".join(subject_text.lower().split()[:2]))
    if character is None and kind not in SUBJECTLESS:
        return None, "unknown subject"
    mapped = to_predicate(kind, str(fact.get("value", "")), str(fact.get("object", "")), zh)
    if mapped is None:
        return None, "malformed value"
    predicate, value = mapped
    quote = str(fact.get("quote", ""))
    ws, we = window
    found = locate(chapter.body[ws:we], quote)
    if found is not None:
        start, end = ws + found.start, ws + found.end
        method = found.method
    else:
        whole = locate(chapter.body, quote)
        if whole is None:
            return None, "quote not found"
        start, end, method = whole.start, whole.end, whole.method
    try:
        confidence = max(0.0, min(1.0, float(fact.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    subject_key = character.id if character else subject_text.lower()
    key = (
        f"{chapter.id}|{chapter.version}|{extractor}|{subject_key}|{predicate}|{start}|{end}|"
        f"{value}"
    )
    details: dict[str, Any] = {"quote_match": method}
    try:
        offset = max(0, min(36500, int(fact.get("day_offset") or 0)))
    except (TypeError, ValueError):
        offset = 0
    if offset:
        details["day_offset"] = offset
    effective_day = None if chapter.story_day is None else chapter.story_day + offset
    obj = str(fact.get("object", "")).strip()
    if obj:
        details["object"] = obj
    if predicate == "hair_color" and (
        obj.lower() == "change" or _DYE.search(chapter.body[start:end])
    ):
        details["change"] = True
    return (
        ExtractedClaim(
            id=str(uuid.uuid5(CLAIM_NAMESPACE, key)),
            chapter_id=chapter.id,
            chapter_version=chapter.version,
            subject_id=character.id if character else "",
            subject_text=subject_text or "world",
            predicate=predicate,
            value=value[:500],
            raw_value=str(fact.get("value", ""))[:500],
            modality=modality,
            confidence=confidence,
            effective_day=effective_day,
            time_certainty="unknown" if chapter.story_day is None else "chapter_day",
            extractor=extractor,
            spans=(Span(chapter.id, chapter.version, start, end, chapter.body[start:end]),),
            details=details,
        ),
        "",
    )
