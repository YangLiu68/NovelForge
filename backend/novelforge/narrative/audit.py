"""Story-logic audit: why does each character act, does it fit who they are, does the plot hold?

The surface checks elsewhere in NovelForge compare stated facts (grey eyes, then green). This
module checks the reasons behind actions, which only an LLM can read, and keeps the LLM honest
with deterministic checks at every step:

1. notes     per chapter: what the text establishes about each character (background,
             personality, goals, wounds, situation, relationships, knowledge), each with a quote.
             The author's character sheet is added as `sheet` notes.
2. beats     per chapter: key actions (who, what, quote, hostile?, cost), setups planted, a
             one-line summary, tension 1-5, reader emotions, and the chapter-ending hook.
3. motives   per chapter: for every beat by a listed character, the likely motives (grounded in
             note IDs from this or earlier chapters), conflicting notes, and a verdict:
             consistent | unmotivated | contradicts | malice_without_cause.
4. later     for every problem verdict: does a later chapter reveal the reason? Then it is a
             planted reveal (`delayed`), not a flaw. The later note must name the beat's
             target or share words with the beat, or it does not count.
5. plot      over the whole story: knowledge leaks, deus ex machina, dangling setups, broken
             causality, each tied to beat / setup / note IDs. A long novel is checked in
             windows of chapters, with a separate payoff check per setup.
6. pacing    deterministic, from the tension curve and hooks: flat stretches, missing hooks.
7. plan      revisions for the worst problems (setups, rewritten motives, a setback that opens
             an opportunity, reversals, cliffhangers...), each tied to the problems it fixes.

Checks the code (not the model) applies: every quote must be found in the chapter (exact,
normalised, or as one clearly matching sentence; the stored span is always the author's text);
characters must resolve to the cast; cited IDs must exist and must not come from a later chapter
than the beat; a note quoting the beat itself cannot be its motive (circular); a
"consistent" verdict that cites nothing becomes `unverified`, a "contradicts"
that names no conflicting note becomes `unmotivated`, "malice" on a beat that harms no one becomes
`unmotivated`; a hook must be at the end of the chapter. Everything dropped is kept in `rejected`
with the reason.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from novelforge.core.domain import ChapterRef
from novelforge.core.lang import detect_language
from novelforge.core.text import split_passages, tokens
from novelforge.extraction.verify import locate_sentence
from novelforge.llm.base import LLM, LLMError
from novelforge.narrative import prompts as P
from novelforge.narrative.schema import (
    BEATS_SCHEMA,
    EMOTIONS,
    LATER_SCHEMA,
    LEAK_SCHEMA,
    MOTIVE_SCHEMA,
    NOTE_KINDS,
    NOTES_SCHEMA,
    PAYOFF_SCHEMA,
    PLAN_SCHEMA,
    PLOT_CALL_KINDS,
    PLOT_KINDS,
    PLOT_SCHEMA,
    PROBLEM_VERDICTS,
    RESCUE_SCHEMA,
    SHAPE_SCHEMA,
    TECHNIQUES,
)

KIND_LABELS = {
    "zh": {
        "background": "身世",
        "personality": "性格",
        "goal": "目标",
        "wound": "创伤",
        "situation": "处境",
        "relationship": "关系",
        "knowledge": "信息",
        "sheet": "设定",
    },
    "en": {k: k for k in (*NOTE_KINDS, "sheet")},
}


@dataclass(frozen=True)
class CastMember:
    name: str
    aliases: tuple[str, ...] = ()
    description: str = ""  # the author's character design, if any


@dataclass
class Note:
    id: str
    character: str
    kind: str  # one of NOTE_KINDS, or "sheet"
    text: str
    chapter: int | None  # None for the character sheet
    quote: str | None = None
    start: int | None = None
    end: int | None = None
    located: str | None = None  # exact | normalized | sentence


@dataclass
class Beat:
    id: str
    chapter: int
    character: str
    listed: bool
    action: str
    quote: str
    start: int
    end: int
    hostile: bool
    target: str
    cost: str
    located: str
    resolves_crisis: bool = False
    uses_secret: bool = False
    secret: str = ""


@dataclass
class Setup:
    id: str
    chapter: int
    text: str
    quote: str
    start: int
    end: int
    key: str = ""  # its core object or person, a word that occurs in the chapter


@dataclass
class Pulse:
    chapter: int
    summary: str
    tension: int
    emotions: list[str]
    hook: bool
    hook_quote: str | None = None
    hook_start: int | None = None
    hook_end: int | None = None


@dataclass
class Judgement:
    beat: str
    model_verdict: str
    verdict: str
    severity: int
    reasoning: str
    motives: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    fixes: list[str]
    explained_by: str | None = None
    explained_why: str | None = None
    checks: list[str] = field(default_factory=list)


@dataclass
class Evidence:
    chapter: int
    start: int
    end: int
    quote: str
    role: str  # beat | conflict | setup | knowledge | hook | chapter


@dataclass
class Issue:
    id: str
    family: str  # character | plot | pacing
    kind: str
    chapter: int
    chapters: list[int]
    character: str | None
    severity: int
    title: str
    explanation: str
    evidence: list[Evidence]
    refs: list[str]
    fixes: list[str]


@dataclass
class Suggestion:
    targets: list[str]
    chapter: int
    technique: str
    change: str
    why: str
    sample: str


@dataclass
class StoryAudit:
    language: str
    llm: str
    prompt_version: str
    chapters: list[dict[str, Any]]
    cast: list[str]
    notes: list[Note] = field(default_factory=list)
    beats: list[Beat] = field(default_factory=list)
    setups: list[Setup] = field(default_factory=list)
    pulses: list[Pulse] = field(default_factory=list)
    judgements: list[Judgement] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def beat(self, beat_id: str) -> Beat | None:
        return next((b for b in self.beats if b.id == beat_id), None)


class _Usage:
    def __init__(self) -> None:
        self.calls = self.input_tokens = self.output_tokens = 0
        self.cost: float | None = 0.0
        self.latency_ms = 0.0
        self.by_stage: dict[str, int] = {}


class StoryAuditor:
    def __init__(
        self,
        chapters: list[ChapterRef],
        cast: list[CastMember],
        llm: LLM,
        language: str | None = None,
        max_chars: int = 2400,
        progress: Callable[[str], None] | None = None,
        plot_window: int = 150,
    ):
        self.chapters = sorted(chapters, key=lambda c: c.number)
        self.by_number = {c.number: c for c in self.chapters}
        # Sorted, so the same novel gives byte-identical prompts from files or the database
        # (which is what lets a recorded run replay).
        self.cast = sorted(cast, key=lambda m: m.name)
        self.llm = llm
        self.lang = language or detect_language("\n".join(c.body for c in self.chapters[:3]))
        if self.lang not in ("zh", "en"):
            self.lang = "en"
        self.max_chars = max_chars
        self.plot_window = plot_window
        self.progress = progress or (lambda _msg: None)
        self.L = P.LABELS[self.lang]
        zh = self.lang == "zh"
        self._paren = (lambda x: f"（{x}）") if zh else (lambda x: f" ({x}) ")
        self._colon = "：" if zh else ": "
        self._q = (lambda x: f"「{x}」") if zh else (lambda x: f'"{x}"')
        self._usage = _Usage()
        self._leaks: list[dict[str, Any]] = []
        self._names: dict[str, str] = {}
        for m in cast:
            for form in (m.name, *m.aliases):
                if form.strip():
                    self._names.setdefault(form.strip(), m.name)
        self.audit = StoryAudit(
            language=self.lang,
            llm=llm.name,
            prompt_version=P.PROMPT_VERSION,
            chapters=[{"number": c.number, "title": c.title} for c in self.chapters],
            cast=[m.name for m in self.cast],
        )

    # ------------------------------------------------------------------ helpers

    def resolve(self, raw: str) -> str | None:
        raw = (raw or "").strip()
        if raw in self._names:
            return self._names[raw]
        # "沈知微（女主）" is 沈知微; "沈若兰的父亲" / "Jo's sister" is not 沈若兰 / Jo.
        hits = {
            name
            for form, name in self._names.items()
            if len(form) >= 2
            and form in raw
            and not re.search(re.escape(form) + r"(?:的|['’]s\b)", raw)
        }
        return hits.pop() if len(hits) == 1 else None

    def _reject(self, stage: str, reason: str, item: Any, chapter: int | None = None) -> None:
        self.audit.rejected.append(
            {"stage": stage, "chapter": chapter, "reason": reason, "item": item}
        )

    def _call(self, stage: str, system: str, prompt: str, schema: dict[str, Any]) -> dict | None:
        u = self._usage
        try:
            result = self.llm.generate_json(system, prompt, schema, max_tokens=4000)
        except LLMError as exc:
            # A replay that cannot answer the very first call is replaying a different text: fail.
            # Later misses (a stage whose input changed with the checks) are recorded and skipped.
            first = exc.kind == "not_recorded" and u.calls == 0
            if exc.kind in ("transport", "config") or first:
                raise
            self.audit.errors.append(f"{stage}: {exc}")
            return None
        u.calls += 1
        u.by_stage[stage] = u.by_stage.get(stage, 0) + 1
        u.input_tokens += result.input_tokens
        u.output_tokens += result.output_tokens
        u.latency_ms += result.latency_ms
        u.cost = None if u.cost is None or result.cost_usd is None else u.cost + result.cost_usd
        if not isinstance(result.data, dict):
            self.audit.errors.append(f"{stage}: answer is not a JSON object")
            return None
        return result.data

    def _windows(self, body: str) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        start = end = None
        size = 0
        for p in split_passages(body):
            n = len(p.text)
            if start is not None and size + n > self.max_chars:
                out.append((start, end))
                start, size = None, 0
            if start is None:
                start = p.start
            end = p.end
            size += n
        if start is not None:
            out.append((start, end))
        return out or [(0, len(body))]

    def _locate(self, chapter: ChapterRef, quote: str):
        if not isinstance(quote, str) or not quote.strip():
            return None
        return locate_sentence(chapter.body, quote)

    def _cast_block(self) -> str:
        lines = []
        for m in self.cast:
            alias = f"（{self.L['aliases']}：{'、'.join(m.aliases)}）" if m.aliases else ""
            if self.lang == "en" and m.aliases:
                alias = f" ({self.L['aliases']}: {', '.join(m.aliases)})"
            lines.append(f"- {m.name}{alias}")
        return f"{self.L['cast']}:\n" + "\n".join(lines)

    def _chapter_head(self, ch: ChapterRef) -> str:
        head = self.L["chapter"].format(n=ch.number)
        return f"{head}《{ch.title}》" if self.lang == "zh" else f"{head}: {ch.title}"

    def _note_line(self, n: Note) -> str:
        kind = KIND_LABELS[self.lang].get(n.kind, n.kind)
        where = (
            self.L["sheet"]
            if n.chapter is None
            else f"{self.L['chapter'].format(n=n.chapter)}·{kind}"
        )
        return f"  {n.id}{self._paren(where)}{n.text}"

    def _beat_line(self, b: Beat) -> str:
        where = self.L["chapter"].format(n=b.chapter)
        return f"{b.id}{self._paren(where)}{b.character}{self._colon}{b.action}"

    # ------------------------------------------------------------------ stages

    def sheet_notes(self) -> None:
        for m in self.cast:
            text = _CJK_GAP.sub("", " ".join(m.description.split()))
            if not text:
                continue
            parts = [p for p in _sentences(text) if p.strip()]
            for part in parts:
                self.audit.notes.append(
                    Note(
                        id=f"N{len(self.audit.notes) + 1}",
                        character=m.name,
                        kind="sheet",
                        text=part.strip(),
                        chapter=None,
                    )
                )

    def notes_stage(self, ch: ChapterRef) -> None:
        seen: set[tuple[str, int, int]] = {
            (n.character, n.start or -1, n.end or -1)
            for n in self.audit.notes
            if n.chapter == ch.number
        }
        for s, e in self._windows(ch.body):
            prompt = (
                f"{self._cast_block()}\n\n{self._chapter_head(ch)} {self.L['text']}:\n"
                f"{ch.body[s:e]}"
            )
            data = self._call("notes", P.NOTES[self.lang], prompt, NOTES_SCHEMA)
            for item in (data or {}).get("notes", []) or []:
                if not isinstance(item, dict):
                    continue
                who = self.resolve(item.get("character", ""))
                if who is None:
                    self._reject("notes", "character not in the cast", item, ch.number)
                    continue
                if item.get("kind") not in NOTE_KINDS or not str(item.get("text", "")).strip():
                    self._reject("notes", "bad kind or empty text", item, ch.number)
                    continue
                loc = self._locate(ch, item.get("quote", ""))
                if loc is None:
                    self._reject("notes", "quote not found in the chapter", item, ch.number)
                    continue
                key = (who, loc.start, loc.end)
                if key in seen:
                    continue
                seen.add(key)
                self.audit.notes.append(
                    Note(
                        id=f"N{len(self.audit.notes) + 1}",
                        character=who,
                        kind=item["kind"],
                        text=str(item["text"]).strip(),
                        chapter=ch.number,
                        quote=ch.body[loc.start : loc.end],
                        start=loc.start,
                        end=loc.end,
                        located=loc.method,
                    )
                )

    def _chapter_prompt(self, ch: ChapterRef, s: int, e: int) -> str:
        return f"{self._cast_block()}\n\n{self._chapter_head(ch)} {self.L['text']}:\n{ch.body[s:e]}"

    def beats_stage(self, ch: ChapterRef) -> None:
        for s, e in self._windows(ch.body):
            prompt = self._chapter_prompt(ch, s, e)
            data = self._call("beats", P.BEATS[self.lang], prompt, BEATS_SCHEMA) or {}
            for item in (data.get("beats") or [])[:8]:
                self._add_beat(ch, item)

    def shape_stage(self, ch: ChapterRef) -> None:
        summaries, tensions, emotions = [], [], []
        hook: tuple[bool, Any] = (False, None)
        windows = self._windows(ch.body)
        for i, (s, e) in enumerate(windows):
            prompt = self._chapter_prompt(ch, s, e)
            data = self._call("shape", P.SHAPE[self.lang], prompt, SHAPE_SCHEMA) or {}
            if str(data.get("summary", "")).strip():
                summaries.append(str(data["summary"]).strip())
            if isinstance(data.get("tension"), int):
                tensions.append(min(5, max(1, data["tension"])))
            emotions += [x for x in data.get("emotions", []) or [] if x in EMOTIONS]
            for item in data.get("setups") or []:
                self._add_setup(ch, item)
            if i == len(windows) - 1:
                h = data.get("hook") or {}
                if h.get("present"):
                    loc = self._locate(ch, h.get("quote", ""))
                    if loc is None:
                        self._reject("shape", "hook quote not found", h, ch.number)
                    elif loc.end < len(ch.body) * 0.7:
                        self._reject("shape", "hook is not at the chapter's end", h, ch.number)
                    else:
                        hook = (True, loc)
        loc = hook[1]
        self.audit.pulses.append(
            Pulse(
                chapter=ch.number,
                summary=" ".join(summaries),
                tension=max(tensions) if tensions else 0,
                emotions=sorted(set(emotions)),
                hook=hook[0],
                hook_quote=ch.body[loc.start : loc.end] if loc else None,
                hook_start=loc.start if loc else None,
                hook_end=loc.end if loc else None,
            )
        )

    def _add_beat(self, ch: ChapterRef, item: Any) -> None:
        if not isinstance(item, dict) or not str(item.get("action", "")).strip():
            self._reject("beats", "empty beat", item, ch.number)
            return
        raw = str(item.get("character", "")).strip()
        who = self.resolve(raw)
        if not raw:
            self._reject("beats", "beat without a character", item, ch.number)
            return
        loc = self._locate(ch, item.get("quote", ""))
        if loc is None:
            self._reject("beats", "quote not found in the chapter", item, ch.number)
            return
        if any(
            b.chapter == ch.number and b.start == loc.start and b.character == (who or raw)
            for b in self.audit.beats
        ):
            return
        secret = _nothing_to_empty(item.get("secret"))
        self.audit.beats.append(
            Beat(
                id=f"B{len(self.audit.beats) + 1}",
                chapter=ch.number,
                character=who or raw,
                listed=who is not None,
                action=str(item["action"]).strip(),
                quote=ch.body[loc.start : loc.end],
                start=loc.start,
                end=loc.end,
                hostile=bool(item.get("hostile")),
                target=_nothing_to_empty(item.get("target")),
                cost=_nothing_to_empty(item.get("cost")),
                located=loc.method,
                resolves_crisis=bool(item.get("resolves_crisis")),
                uses_secret=bool(item.get("uses_secret")) and bool(secret),
                secret=secret,
            )
        )

    def _add_setup(self, ch: ChapterRef, item: Any) -> None:
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            return
        loc = self._locate(ch, item.get("quote", ""))
        if loc is None:
            self._reject("shape", "setup quote not found", item, ch.number)
            return
        if any(s.chapter == ch.number and s.start == loc.start for s in self.audit.setups):
            return
        key = str(item.get("key", "") or "").strip().strip("“”\"'「」")
        if key and key not in ch.body:
            self._reject("shape", "setup key is not a word of the chapter", item, ch.number)
            key = ""
        self.audit.setups.append(
            Setup(
                id=f"S{len(self.audit.setups) + 1}",
                chapter=ch.number,
                text=str(item["text"]).strip(),
                quote=ch.body[loc.start : loc.end],
                start=loc.start,
                end=loc.end,
                key=key,
            )
        )

    def _file_for(self, character: str, upto: int) -> list[Note]:
        """The character's notes visible at chapter `upto`: sheet, then text notes up to it,
        plus other characters' relationship notes that name them."""
        own = [
            n
            for n in self.audit.notes
            if n.character == character and (n.chapter is None or n.chapter <= upto)
        ]
        sheet = [n for n in own if n.chapter is None]
        text = [n for n in own if n.chapter is not None][-24:]
        forms = [character] + [f for f, name in self._names.items() if name == character]
        about = [
            n
            for n in self.audit.notes
            if n.character != character
            and n.kind == "relationship"
            and n.chapter is not None
            and n.chapter <= upto
            and any(f in n.text or (n.quote and f in n.quote) for f in forms)
        ][-6:]
        return sheet + text + about

    def motives_stage(self, ch: ChapterRef) -> None:
        for b in [b for b in self.audit.beats if b.chapter == ch.number and b.listed]:
            notes = self._file_for(b.character, ch.number)
            lines = [
                f"{self.L['beat']} {self._beat_line(b)}",
                f"  {self.L['quote']}{self._colon}{self._q(b.quote)}",
            ]
            if b.target:
                lines.append(f"  {self.L['target']}{self._colon}{b.target}")
            if b.cost:
                lines.append(f"  {self.L['cost']}{self._colon}{b.cost}")
            lines.append(f"\n{self.L['file']}: {b.character}")
            lines += [self._note_line(n) for n in notes] or ["  —"]
            data = self._call("motives", P.MOTIVES[self.lang], "\n".join(lines), MOTIVE_SCHEMA)
            if not data or "is_choice" not in data:
                self.audit.errors.append(f"motives: no judgement for {b.id}")
                continue
            self._judge(b, data, {n.id: n for n in notes})

    def leak_stage(self, ch: ChapterRef) -> None:
        """For each beat that uses a secret: where did the actor learn it? A source must be a
        cited note of theirs or a sentence earlier in this chapter; otherwise it is a leak."""
        for b in [
            b
            for b in self.audit.beats
            if b.chapter == ch.number and b.listed and b.uses_secret and self._established(b)
        ]:
            notes = self._file_for(b.character, ch.number)
            before = ch.body[max(0, b.start - 1500) : b.start]
            lines = [
                f"{self.L['beat']} {self._beat_line(b)}",
                f"  {self.L['quote']}{self._colon}{self._q(b.quote)}",
                f"  {self.L['secret']}{self._colon}{b.secret}",
                f"\n{self.L['file']}: {b.character}",
                *([self._note_line(n) for n in notes] or ["  —"]),
                f"\n{self.L['before']}:\n{before}",
            ]
            data = self._call("leak", P.LEAK[self.lang], "\n".join(lines), LEAK_SCHEMA)
            if not data or "how" not in data:
                self.audit.errors.append(f"leak: no answer for {b.id}")
                continue
            visible = {n.id: n for n in notes}
            cited = [
                nid
                for nid in _ids(data.get("source_notes"), "N")
                if nid in visible and not _same_passage(visible[nid], b)
            ]
            quote = str(data.get("source_quote", "") or "").strip()
            loc = self._locate(ch, quote) if quote else None
            earlier = loc is not None and loc.end <= b.start
            if data.get("how") != "none" and (cited or earlier):
                continue
            self._leaks.append(
                {
                    "kind": "knowledge_leak",
                    "chapter": b.chapter,
                    "character": b.character,
                    "refs": [b.id],
                    "explanation": f"{b.secret}"
                    + (f"（{data.get('source')}）" if data.get("source") else ""),
                    "severity": 3,
                    "fixes": [],
                }
            )

    def _established(self, b: Beat) -> bool:
        """Was the secret set down in an earlier chapter? Only then can using it be a leak;
        information that first appears in the beat's own chapter is a reveal. At least half of
        the secret's content tokens (Chinese bigrams, English words; names left out) must occur
        in one earlier chapter."""
        names = {t for f in self._names for t in tokens(f)}
        wanted = set(tokens(b.secret)) - names
        if not wanted:
            return False
        for c in self.chapters:
            if c.number >= b.chapter:
                break
            have = set(tokens(_squash(c.body))) | set(tokens(c.body))
            if len(wanted & have) * 2 >= len(wanted):
                return True
        return False

    def _judge(self, b: Beat, item: dict[str, Any], visible: dict[str, Note]) -> None:
        """Turn the model's answers to the sub-questions into a verdict (see _verdict)."""
        checks: list[str] = []

        def valid(ids: Any, role: str) -> list[str]:
            out = []
            for nid in _ids(ids, "N"):
                n = visible.get(nid)
                if n is None:
                    checks.append(f"dropped {role} {nid}: not in the file shown for {b.id}")
                elif role == "reason" and _same_passage(n, b):
                    # A note read off the act itself ("kind-hearted", quoting the gift) cannot be
                    # the reason for the act: that is circular.
                    checks.append(f"dropped reason {nid}: it quotes the beat itself (circular)")
                elif role == "reason" and _NO_REASON.search(f"{n.text} {n.quote or ''}"):
                    checks.append(f"dropped reason {nid}: dislike or whim is not a motive")
                else:
                    out.append(nid)
            return out

        reason = str(item.get("reason", "") or "").strip()
        raw_reasons = _ids(item.get("reason_notes"), "N")
        raw_against = _ids(item.get("against_notes"), "N")
        reasons = valid(item.get("reason_notes"), "reason")
        stated = bool(reason)
        if reason and _NO_REASON.search(reason):
            checks.append("the stated reason is dislike or whim, which is not a motive")
            reasons, stated = [], False
        against = valid(item.get("against_notes"), "conflict")
        choice = bool(item.get("is_choice")) or bool(against) or b.hostile
        model_verdict = _verdict(
            bool(item.get("is_choice")) or b.hostile,
            bool(raw_reasons),
            bool(reason),
            b.hostile,
            bool(raw_against),
        )
        verdict = _verdict(choice, bool(reasons), stated, b.hostile, bool(against))
        fixes = [str(f).strip() for f in item.get("fixes") or [] if str(f).strip()][:3]
        self.audit.judgements.append(
            Judgement(
                beat=b.id,
                model_verdict=model_verdict,
                verdict=verdict,
                severity=_severity(item.get("severity")),
                reasoning=str(item.get("explanation", "") or "").strip(),
                motives=[{"motive": reason, "support": reasons}] if reason else [],
                conflicts=[
                    {"note": nid, "why": str(item.get("against", "") or "").strip()}
                    for nid in against
                ],
                fixes=fixes if verdict in PROBLEM_VERDICTS else [],
                checks=checks,
            )
        )

    def later_stage(self) -> None:
        for j in self.audit.judgements:
            if j.verdict not in PROBLEM_VERDICTS:
                continue
            b = self.audit.beat(j.beat)
            later = [
                n
                for n in self.audit.notes
                if n.character == b.character and n.chapter is not None and n.chapter > b.chapter
            ][:20]
            if not later:
                continue
            lines = [
                f"{self.L['beat']} {self._beat_line(b)}",
                f"  {self.L['quote']}{self._colon}{self._q(b.quote)}",
                f"  {j.reasoning}",
                f"\n{self.L['later_file']}:",
                *[self._note_line(n) for n in later],
            ]
            data = self._call("later", P.LATER[self.lang], "\n".join(lines), LATER_SCHEMA) or {}
            found = _ids(data.get("explained_by"), "N")
            if not found:
                continue
            nid = found[0]
            note = next((n for n in later if n.id == nid), None)
            if note is None:
                j.checks.append(f"later explanation {nid} is not a later note of {b.character}")
                continue
            if not self._relevant(note, b):
                j.checks.append(
                    f"later explanation {nid} names neither the beat's target nor anything in it"
                )
                continue
            j.explained_by, j.explained_why = nid, str(data.get("why", "")).strip()
            j.checks.append(f"explained later by {nid}: delayed reveal, not a flaw")
            j.verdict = "delayed"
            j.fixes = []

    def _relevant(self, note: Note, b: Beat) -> bool:
        """Does a later note plausibly speak to this beat? It must name the beat's target (any
        of their names) or share a content word / Chinese bigram with what the beat says. Small
        models otherwise "explain" any act with any later fact about the character."""
        text = f"{note.text} {note.quote or ''}"
        if b.target:
            who = self.resolve(b.target)
            forms = [b.target] + (
                [f for f, name in self._names.items() if name == who] if who else []
            )
            if any(len(f) >= 2 and f in text for f in forms):
                return True
        own = set(tokens(f"{b.action} {b.quote}"))
        names = {t for f in self._names for t in tokens(f)}
        return bool((set(tokens(text)) & own) - names)

    def _plot_prompt(self, beats: list[Beat], setups: list[Setup], known: list[Note]) -> str:
        ch = self.L["chapter"]
        lines = [f"{self.L['beats']}:"]
        lines += [self._beat_line(b) for b in beats]
        if setups:
            lines.append(f"\n{self.L['setups']}:")
            lines += [f"{s.id}{self._paren(ch.format(n=s.chapter))}{s.text}" for s in setups]
        if known:
            lines.append(f"\n{self.L['knowledge']}:")
            lines += [
                f"{n.id}{self._paren(ch.format(n=n.chapter))}{n.character}{self._colon}{n.text}"
                for n in known
            ]
        return "\n".join(lines)

    def _beat_windows(self, beats: list[Beat]) -> list[list[Beat]]:
        """Consecutive whole chapters with at most `plot_window` beats (one chapter can exceed)."""
        out: list[list[Beat]] = []
        current: list[Beat] = []
        for number in sorted({b.chapter for b in beats}):
            chapter = [b for b in beats if b.chapter == number]
            if current and len(current) + len(chapter) > self.plot_window:
                out.append(current)
                current = []
            current += chapter
        if current:
            out.append(current)
        return out

    def plot_stage(self) -> list[dict[str, Any]]:
        """Knowledge leaks and broken causality from one call per window of chapters (a single
        call for most novels); dangling setups from a payoff check per setup; deus ex machina
        from beats that resolve a crisis by someone never seen before. Every prompt stays
        bounded however long the novel is."""
        a = self.audit
        if not a.beats:
            return []
        known = [n for n in a.notes if n.kind == "knowledge" and n.chapter is not None]
        out: list[dict[str, Any]] = []
        for window in self._beat_windows(a.beats):
            last = window[-1].chapter
            seen = [n for n in known if n.chapter <= last][-60:]
            prompt = self._plot_prompt(window, [], seen)
            data = self._call("plot", P.PLOT[self.lang], prompt, PLOT_SCHEMA) or {}
            out += self._plot_items(data, dangling=False)
        return out + self._leaks + self._rescues() + self._unpaid_setups()

    def _first_seen(self, b: Beat) -> bool:
        """True if the actor is named in an earlier chapter (any of their names, or the core of
        an unlisted descriptor without honorifics)."""
        forms = [b.character]
        if b.listed:
            forms += [f for f, name in self._names.items() if name == b.character]
        forms += [_HONORIFIC.sub("", f) for f in forms]
        forms = [f for f in forms if len(f) >= 2]
        earlier = [c.body for c in self.chapters if c.number < b.chapter]
        return any(f in body for f in forms for body in earlier)

    def _rescues(self) -> list[dict[str, Any]]:
        out = []
        for b in self.audit.beats:
            if not b.resolves_crisis or self._first_seen(b):
                continue
            lines = [
                f"{self.L['beat']} {self._beat_line(b)}",
                f"  {self.L['quote']}{self._colon}{self._q(b.quote)}",
            ]
            data = self._call("rescue", P.RESCUE[self.lang], "\n".join(lines), RESCUE_SCHEMA)
            if not (data or {}).get("deus_ex_machina"):
                continue
            out.append(
                {
                    "kind": "deus_ex_machina",
                    "chapter": b.chapter,
                    "character": b.character if b.listed else None,
                    "refs": [b.id],
                    "explanation": str(data.get("why", "") or "").strip() or b.action,
                    "severity": 3,
                    "fixes": [str(f).strip() for f in data.get("fixes") or [] if str(f).strip()],
                }
            )
        return out

    def _unpaid_setups(self) -> list[dict[str, Any]]:
        """A setup with a key word is paid off if the word comes back in a later chapter (code,
        no model); one without a usable key gets a payoff check against the later beats."""
        out = []
        for setup in self.audit.setups:
            later = [c for c in self.chapters if c.number > setup.chapter]
            if not later:
                continue  # planted in the last chapter: an open ending, not a dangling setup
            if setup.key:
                # Punctuation inside a word is typography: “青”，“雀” is still 青雀.
                if any(_squash(setup.key) in _squash(c.body) for c in later):
                    continue
            elif self._paid_by_model(setup):
                continue
            out.append(
                {
                    "kind": "dangling_setup",
                    "chapter": setup.chapter,
                    "character": None,
                    "refs": [setup.id],
                    "explanation": setup.text,
                    "severity": 2,
                    "fixes": [],
                }
            )
        return out

    def _paid_by_model(self, setup: Setup) -> bool:
        later = [b for b in self.audit.beats if b.chapter > setup.chapter]
        for window in self._beat_windows(later):
            lines = [
                f"{self.L['setups']}:",
                f"{setup.id}{self._paren(self.L['chapter'].format(n=setup.chapter))}{setup.text}",
                f"  {self.L['quote']}{self._colon}{self._q(setup.quote)}",
                f"\n{self.L['beats']}:",
                *[self._beat_line(b) for b in window],
            ]
            data = self._call("payoff", P.PAYOFF[self.lang], "\n".join(lines), PAYOFF_SCHEMA)
            found = _ids((data or {}).get("paid_off_by"), "B")
            if found and found[0] in {b.id for b in window}:
                return True
        return False

    def _plot_items(self, data: dict[str, Any], dangling: bool) -> list[dict[str, Any]]:
        a = self.audit
        ids = {b.id: b for b in a.beats} | {s.id: s for s in a.setups} | {n.id: n for n in a.notes}
        out = []
        allowed = PLOT_KINDS if dangling else PLOT_CALL_KINDS
        for item in data.get("issues", []) or []:
            if not isinstance(item, dict) or item.get("kind") not in allowed:
                self._reject("plot", "bad kind", item)
                continue
            refs = [r for r in _ids(item.get("refs"), "BSN") if r in ids]
            beats = [ids[r] for r in refs if r.startswith("B")]
            setups = [ids[r] for r in refs if r.startswith("S")]
            kind = item["kind"]
            if kind == "dangling_setup" and not dangling:
                continue  # each setup gets its own payoff check
            if kind == "dangling_setup" and not setups:
                self._reject("plot", "dangling setup without a setup ID", item)
                continue
            if kind in ("knowledge_leak", "deus_ex_machina") and not beats:
                self._reject("plot", f"{kind} without a beat ID", item)
                continue
            if kind == "causality" and len(beats) < 2:
                self._reject("plot", "causality without a cause and an effect", item)
                continue
            if not refs or not str(item.get("explanation", "")).strip():
                self._reject("plot", "no valid reference or explanation", item)
                continue
            anchors = setups if kind == "dangling_setup" else beats or setups
            chapter = anchors[0].chapter if anchors else item.get("chapter")
            if chapter not in self.by_number:
                self._reject("plot", "chapter out of range", item)
                continue
            who = self.resolve(item.get("character", ""))
            if kind == "knowledge_leak":
                who = beats[0].character
            out.append({**item, "refs": refs, "chapter": chapter, "character": who})
        return out

    def plan_stage(self) -> None:
        a = self.audit
        if not a.issues:
            return
        ch = self.L["chapter"]
        lines = [f"{self.L['summaries']}:"]
        for p in a.pulses:
            hook = self.L["yes"] if p.hook else self.L["no"]
            meta = f"{self.L['tension']} {p.tension}, {self.L['hook']}{self._colon}{hook}"
            lines.append(f"{ch.format(n=p.chapter)}{self._paren(meta)}{p.summary}")
        lines.append(f"\n{self.L['issues']}:")
        for i in a.issues[:12]:
            who = f"{i.character}{self._colon}" if i.character else ""
            where = f"{ch.format(n=i.chapter)}, {i.kind}"
            lines.append(f"{i.id}{self._paren(where)}{who}{i.title} {i.explanation}")
        data = self._call("plan", P.PLAN[self.lang], "\n".join(lines), PLAN_SCHEMA) or {}
        known = {i.id for i in a.issues}
        for item in data.get("suggestions", []) or []:
            if not isinstance(item, dict) or not str(item.get("change", "")).strip():
                continue
            targets = [t for t in _ids(item.get("targets"), "I") if t in known]
            if not targets or item.get("chapter") not in self.by_number:
                self._reject("plan", "no known target or chapter out of range", item)
                continue
            a.suggestions.append(
                Suggestion(
                    targets=targets,
                    chapter=item["chapter"],
                    technique=item["technique"] if item.get("technique") in TECHNIQUES else "other",
                    change=str(item["change"]).strip(),
                    why=str(item.get("why", "")).strip(),
                    sample=str(item.get("sample", "") or "").strip(),
                )
            )

    # ------------------------------------------------------------------ assembly

    def _pacing_issues(self) -> list[dict[str, Any]]:
        """Flat stretches: three or more chapters running at tension <= 2, or a shorter run
        that has a chapter with no conflict at all (tension 1) and ends without a hook.
        Elsewhere, chapters (but the last) that end without a hook."""
        pulses = [p for p in self.audit.pulses if p.tension]
        out: list[dict[str, Any]] = []
        run: list[Pulse] = []
        for p in [*pulses, None]:
            if p is not None and p.tension <= 2:
                run.append(p)
                continue
            dead = any(q.tension == 1 for q in run) and not run[-1].hook if run else False
            if len(run) >= 3 or dead:
                out.append({"kind": "flat_stretch", "pulses": run, "severity": 2})
            run = []
        last = self.chapters[-1].number if self.chapters else None
        flat = {q.chapter for o in out for q in o["pulses"]}
        for p in pulses:
            if not p.hook and p.chapter != last and p.chapter not in flat:
                out.append({"kind": "no_hook", "pulses": [p], "severity": 1})
        return out

    def assemble(self, plot: list[dict[str, Any]]) -> None:
        a = self.audit
        notes = {n.id: n for n in a.notes}
        rows: list[dict[str, Any]] = []
        for j in a.judgements:
            if j.verdict not in PROBLEM_VERDICTS:
                continue
            b = a.beat(j.beat)
            ev = [Evidence(b.chapter, b.start, b.end, b.quote, "beat")]
            for c in j.conflicts:
                n = notes[c["note"]]
                if n.chapter is not None:
                    ev.append(Evidence(n.chapter, n.start, n.end, n.quote, "conflict"))
            rows.append(
                dict(
                    family="character",
                    kind=j.verdict,
                    chapter=b.chapter,
                    chapters=[b.chapter],
                    character=b.character,
                    severity=j.severity,
                    title=b.action,
                    explanation=j.reasoning,
                    evidence=ev,
                    refs=[b.id, *[c["note"] for c in j.conflicts]],
                    fixes=j.fixes,
                )
            )
        for item in plot:
            ev = []
            for r in item["refs"]:
                x = next((o for o in (*a.beats, *a.setups, *a.notes) if o.id == r), None)
                if x is not None and getattr(x, "chapter", None) is not None:
                    role = {"B": "beat", "S": "setup"}.get(r[0], "knowledge")
                    ev.append(Evidence(x.chapter, x.start, x.end, x.quote, role))
            rows.append(
                dict(
                    family="plot",
                    kind=item["kind"],
                    chapter=item["chapter"],
                    chapters=sorted({e.chapter for e in ev} | {item["chapter"]}),
                    character=item.get("character"),
                    severity=_severity(item.get("severity")),
                    title=str(item["explanation"]).strip(),
                    explanation=str(item["explanation"]).strip(),
                    evidence=ev,
                    refs=item["refs"],
                    fixes=[str(f).strip() for f in item.get("fixes") or [] if str(f).strip()][:3],
                )
            )
        for item in self._pacing_issues():
            ps = item["pulses"]
            ev = []
            for p in ps:
                body = self.by_number[p.chapter].body
                tail = split_passages(body)[-1]
                ev.append(Evidence(p.chapter, tail.start, tail.end, tail.text, "chapter"))
            chs = [p.chapter for p in ps]
            if self.lang == "zh":
                where = f"第 {chs[0]} 章" if len(chs) == 1 else f"第 {chs[0]}–{chs[-1]} 章"
                title = (
                    f"{where}紧张度只有 {'、'.join(str(p.tension) for p in ps)}"
                    + ("，章末没有钩子" if not ps[-1].hook else "")
                    if item["kind"] == "flat_stretch"
                    else f"{where}章末没有钩子"
                )
            else:
                where = f"Chapter {chs[0]}" if len(chs) == 1 else f"Chapters {chs[0]}-{chs[-1]}"
                title = (
                    f"{where}: tension {', '.join(str(p.tension) for p in ps)}"
                    + ("; no ending hook" if not ps[-1].hook else "")
                    if item["kind"] == "flat_stretch"
                    else f"{where}: no ending hook"
                )
            rows.append(
                dict(
                    family="pacing",
                    kind=item["kind"],
                    chapter=chs[0],
                    chapters=chs,
                    character=None,
                    severity=item["severity"],
                    title=title,
                    explanation=" / ".join(p.summary for p in ps if p.summary),
                    evidence=ev,
                    refs=[],
                    fixes=[],
                )
            )
        family_order = {"character": 0, "plot": 1, "pacing": 2}
        rows.sort(key=lambda r: (-r["severity"], family_order[r["family"]], r["chapter"]))
        a.issues = [Issue(id=f"I{i}", **r) for i, r in enumerate(rows, start=1)]

    def run(self) -> StoryAudit:
        started = time.perf_counter()
        self.sheet_notes()
        for ch in self.chapters:
            self.progress(f"notes, beats, shape: chapter {ch.number}")
            self.notes_stage(ch)
            self.beats_stage(ch)
            self.shape_stage(ch)
        for ch in self.chapters:
            self.progress(f"motives and secrets: chapter {ch.number}")
            self.motives_stage(ch)
            self.leak_stage(ch)
        self.progress("later explanations")
        self.later_stage()
        self.progress("plot")
        plot = self.plot_stage()
        self.assemble(plot)
        self.progress("revision plan")
        self.plan_stage()
        u = self._usage
        self.audit.usage = {
            "calls": u.calls,
            "calls_by_stage": u.by_stage,
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cost_usd": None if u.cost is None else round(u.cost, 6),
            "llm_seconds": round(u.latency_ms / 1000, 1),
            "seconds": round(time.perf_counter() - started, 1),
        }
        return self.audit


_NOTHING = {"", "无", "没有", "暂无", "none", "n/a", "nothing", "-", "—"}


def _nothing_to_empty(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower().strip("。.") in _NOTHING else text


def _same_passage(n: Note, b: Beat) -> bool:
    return (
        n.chapter == b.chapter
        and n.start is not None
        and n.end is not None
        and n.start < b.end
        and b.start < n.end
    )


# Dislike, whim or "just because" is not a motive (the user's rule: no villainy for its own sake).
_NO_REASON = re.compile(
    r"看[^，。]{0,3}不顺眼|不顺眼|说不清|说不上|没来由|无缘无故|天生[^，。]{0,2}坏|就是想看|"
    r"图个(?:乐|痛快|开心)|觉得[^，。]{0,12}有意思|好玩|for no reason|just because|for fun|"
    r"(?:didn't|did not) know why|disliked? (?:her|him|them) on sight",
    re.I,
)
_HONORIFIC = re.compile(r"(?:大人|公子|小姐|姑娘|先生|老爷|夫人|少爷|掌柜)$")
_CJK_GAP = re.compile(r"(?<=[\u4e00-\u9fff，。、；：）])\s+(?=[\u4e00-\u9fff（])")


def _squash(text: str) -> str:
    """Text without spaces and punctuation, for matching a word across typographic breaks."""
    return "".join(ch for ch in text if ch.isalnum())


def _verdict(choice: bool, grounded: bool, stated: bool, hostile: bool, against: bool) -> str:
    """The rule a reader applies, in order: an everyday action needs no reason; a reason the
    text gives (a cited note) settles it; acting against the character without one is a
    contradiction; a reason the model states but cannot ground is unverified (not counted);
    harming someone with no reason at all is villainy for its own sake; anything else that
    needs a reason and has none is unmotivated."""
    if not choice:
        return "routine"
    if grounded:
        return "consistent"
    if against:
        return "contradicts"
    if stated:
        return "unverified"
    return "malice_without_cause" if hostile else "unmotivated"


def _ids(value: Any, prefixes: str) -> list[str]:
    """IDs like B12 / N3 / S1 / I4 from a model's field, which may be a list, a string, or a
    decorated form such as "B5（第 2 章）" or "B3、B4"; in order, without repeats."""
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        for m in re.finditer(rf"(?<![A-Za-z])[{prefixes}]\d+", str(item or "")):
            if m.group() not in out:
                out.append(m.group())
    return out


def _severity(value: Any) -> int:
    return min(3, max(1, value)) if isinstance(value, int) else 2


def _sentences(text: str) -> list[str]:
    """Split an author's description into sentences (Chinese or English full stops)."""
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch in "。！？；" or (ch in ".!?" and len(buf) > 1):
            out.append(buf)
            buf = ""
    if buf.strip():
        out.append(buf)
    return out


def audit_story(
    chapters: list[ChapterRef],
    cast: list[CastMember],
    llm: LLM,
    language: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> StoryAudit:
    return StoryAuditor(chapters, cast, llm, language=language, progress=progress).run()
