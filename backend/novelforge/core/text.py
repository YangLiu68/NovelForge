"""Text utilities. All offsets are Python string (code-point) offsets into the chapter body."""

import hashlib
import re
from dataclasses import dataclass

_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n\s*")
_SENTENCE_END = re.compile(r"[.!?…][\"'”’)]*\s+|\n")


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    text: str


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_body(text: str) -> str:
    """Canonical chapter body: LF newlines, no trailing spaces, no leading/trailing blank lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip("\n")


def split_passages(body: str) -> list[TextSpan]:
    """Paragraph-level spans (blank-line separated), trimmed of surrounding whitespace."""
    blocks: list[tuple[int, int]] = []
    pos = 0
    for brk in _PARAGRAPH_BREAK.finditer(body):
        blocks.append((pos, brk.start()))
        pos = brk.end()
    blocks.append((pos, len(body)))
    spans = []
    for start, end in blocks:
        chunk = body[start:end]
        lead = len(chunk) - len(chunk.lstrip())
        trail = len(chunk) - len(chunk.rstrip())
        s, e = start + lead, end - trail
        if e > s:
            spans.append(TextSpan(s, e, body[s:e]))
    return spans


def sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """Bounds of the sentence(s) containing text[start:end]."""
    s = 0
    for m in _SENTENCE_END.finditer(text, 0, start):
        s = m.end()
    m = _SENTENCE_END.search(text, end)
    e = m.start() + len(m.group(0).rstrip()) if m else len(text)
    return s, e


def inside_dialogue(text: str, pos: int) -> bool:
    """True if `pos` falls inside a quotation in its paragraph (straight or curly quotes)."""
    para_start = text.rfind("\n\n", 0, pos)
    para_start = 0 if para_start < 0 else para_start + 2
    segment = text[para_start:pos]
    if segment.count("“") > segment.count("”"):
        return True
    return segment.count('"') % 2 == 1


_UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

# Matches 1-3 digit numbers and English number words from zero to ninety-nine.
NUMBER_PATTERN = (
    r"(?:\d{1,3}|(?:"
    + "|".join(_TENS)
    + r")(?:[- ](?:"
    + "|".join(_UNITS[1:10])
    + r"))?|"
    + "|".join(sorted(_UNITS, key=len, reverse=True))
    + r")"
)


def parse_number(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    if token in _UNITS:
        return _UNITS.index(token)
    parts = re.split(r"[- ]", token)
    if parts[0] in _TENS:
        value = 20 + 10 * _TENS.index(parts[0])
        if len(parts) == 2 and parts[1] in _UNITS[1:10]:
            return value + _UNITS.index(parts[1])
        if len(parts) == 1:
            return value
    return None


_WORD = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?")
# fmt: off
STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "did", "do", "does", "for",
    "from", "had", "has", "have", "he", "her", "hers", "him", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "me", "my", "no", "not", "of", "on", "or", "our", "she", "so",
    "that", "the", "their", "them", "they", "this", "to", "us", "was", "we", "were", "what",
    "when", "where", "which", "who", "whom", "why", "will", "with", "would", "you", "your",
})
# fmt: on


def stem(word: str) -> str:
    """A tiny, deterministic suffix stripper (not Porter); enough for lexical baselines."""
    for suffix, repl in (
        ("'s", ""),
        ("’s", ""),
        ("ies", "y"),
        ("ied", "y"),
        ("ing", ""),
        ("ed", ""),
        ("es", ""),
        ("s", ""),
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + repl
    return word


def tokens(text: str) -> list[str]:
    """Lowercased, stop-word-free, lightly stemmed word tokens."""
    return [stem(w) for w in _WORD.findall(text.lower()) if w not in STOPWORDS]


_SCENE_BREAK = re.compile(r"^[ \t]*(?:\*[ \t]*\*[ \t]*\*[ \t*]*|-{3,}|#{1,3}[ \t]*)$", re.M)


def split_scenes(body: str) -> list[TextSpan]:
    """Scenes are the parts of a chapter between scene-break lines (`* * *`, `***`, `---`)."""
    spans: list[TextSpan] = []
    pos = 0
    for m in [*_SCENE_BREAK.finditer(body), None]:
        end = m.start() if m else len(body)
        chunk = body[pos:end]
        lead = len(chunk) - len(chunk.lstrip())
        trail = len(chunk) - len(chunk.rstrip())
        s, e = pos + lead, end - trail
        if e > s:
            spans.append(TextSpan(s, e, body[s:e]))
        if m:
            pos = m.end()
    return spans


def number_to_words(n: int) -> str:
    """English words for 0-99 ("thirty-one"); digits above that."""
    if n >= 100 or n < 0:
        return str(n)
    if n < 20:
        return _UNITS[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens - 2] + ("" if ones == 0 else "-" + _UNITS[ones])
