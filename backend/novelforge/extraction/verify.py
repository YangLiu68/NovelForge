"""Find an LLM's quote in the chapter text.

The model is told to copy quotes exactly, but models normalise punctuation and whitespace. The
locator tries an exact match first, then a normalised match (curly quotes and apostrophes,
dashes, whitespace, case) mapped back to original offsets. A quote that cannot be found is
rejected: no fact enters the database without a verifiable source span.
"""

from __future__ import annotations

from dataclasses import dataclass

_TRANSLATE = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "—": "-", "–": "-", "…": "."})
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
