"""Find an LLM's quote in the chapter text.

The model is told to copy quotes exactly, but models normalise punctuation and whitespace. The
locator tries an exact match first, then a normalised match (curly quotes and apostrophes,
dashes, whitespace, case) mapped back to original offsets. A quote that cannot be found is
rejected: no fact enters the database without a verifiable source span.

`locate_sentence` is a looser fallback for the story-logic stages, where small models often
shorten or slightly reword a Chinese quote: it accepts the one sentence of the chapter that is
clearly the quote (character similarity >= 0.8) and returns that sentence's real span, so the
evidence shown is always the author's text, never the model's paraphrase. A quote stitched
together from several sentences keeps its longest sentence that is really in the text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_TRANSLATE = str.maketrans(
    {
        "“": '"', "”": '"', "‘": "'", "’": "'", "—": "-", "–": "-", "…": ".",
        # Chinese punctuation: models often answer with the half-width form (one-to-one only).
        "「": '"', "」": '"', "『": '"', "』": '"', "，": ",", "。": ".", "！": "!", "？": "?",
        "：": ":", "；": ";", "（": "(", "）": ")", "、": ",",
    }
)  # fmt: skip
MIN_QUOTE, MAX_QUOTE = 3, 600


@dataclass(frozen=True)
class Located:
    start: int
    end: int
    method: str  # exact | normalized
    occurrences: int


def _normalized(text: str) -> tuple[str, list[int]]:
    """Normalised text plus, for each of its characters, the index in the original."""
    out: list[str] = []
    index: list[int] = []
    prev_space = False
    for i, ch in enumerate(text.translate(_TRANSLATE)):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            index.append(i)
            prev_space = True
        else:
            low = ch.lower()
            # Keep a one-to-one character map: some lowercasings change length ("İ" -> "i̇").
            out.append(low if len(low) == 1 else ch)
            index.append(i)
            prev_space = False
    return "".join(out), index


def locate(body: str, quote: str) -> Located | None:
    quote = quote.strip()
    if len(quote) >= 2 and quote[0] in '"“' and quote[-1] in '"”' and quote.count('"') == 2:
        quote = quote[1:-1].strip()  # the model wrapped the quote in quotation marks
    if not (MIN_QUOTE <= len(quote) <= MAX_QUOTE):
        return None
    start = body.find(quote)
    if start >= 0:
        return Located(start, start + len(quote), "exact", body.count(quote))
    norm_body, index = _normalized(body)
    norm_quote, _ = _normalized(quote)
    pos = norm_body.find(norm_quote)
    if pos < 0:
        return None
    end_norm = pos + len(norm_quote) - 1
    return Located(index[pos], index[end_norm] + 1, "normalized", norm_body.count(norm_quote))


_PIECE_END = re.compile(r"(?<=[。！？!?；;])|(?<=[.!?][\"'”’])\s+|(?<=[.!?])\s+")


def locate_sentence(body: str, quote: str, min_ratio: float = 0.8) -> Located | None:
    """Exact or normalised match; else, for a quote stitched from several sentences, the
    longest of its sentences that is in the text (method "piece"); else the one sentence that
    clearly matches it (method "sentence")."""
    found = locate(body, quote)
    if found is not None:
        return found
    pieces = [p.strip() for p in _PIECE_END.split(quote.strip()) if len(p.strip()) >= 8]
    if len(pieces) > 1:
        hits = [(loc.end - loc.start, loc) for p in pieces if (loc := locate(body, p))]
        if hits:
            _, best = max(hits, key=lambda h: h[0])
            return Located(best.start, best.end, "piece", best.occurrences)
    from novelforge.core.text import sentence_bounds

    q, _ = _normalized(quote.strip().strip('"“”「」'))
    if len(q) < 6:
        return None
    best: tuple[float, int, int] | None = None
    pos = 0
    while pos < len(body):
        s, e = sentence_bounds(body, pos, pos)
        if e <= pos:
            e = pos + 1
        cand, _ = _normalized(body[s:e])
        if cand.strip():
            m = SequenceMatcher(None, q, cand, autojunk=False)
            # How much of the quote the sentence covers, and how much of the sentence is quoted.
            match = sum(b.size for b in m.get_matching_blocks())
            ratio = match / max(len(q), 1)
            if match / max(len(cand), 1) >= 0.5 and (best is None or ratio > best[0]):
                best = (ratio, s, e)
        pos = e + 1
    if best is None or best[0] < min_ratio:
        return None
    _, s, e = best
    while s < e and body[s].isspace():
        s += 1
    return Located(s, e, "sentence", 1)
