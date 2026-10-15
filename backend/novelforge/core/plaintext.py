"""Plain-text manuscripts: split a .txt novel into chapters (no database access).

Handles the usual shape of a typed or Project Gutenberg text: an optional licence header and
footer, a table of contents, chapter headings on their own line, hard-wrapped paragraphs
separated by blank lines.
"""

import re
from dataclasses import dataclass

from novelforge.core.text import normalize_body

DEFAULT_HEADING = r"^(?:CHAPTER|Chapter) [A-Z0-9IVXLC][A-Za-z0-9-]*\.?(?:[ \t].*)?$"
_GUTENBERG_START = re.compile(r"^\*\*\* ?START OF (?:THE|THIS) PROJECT GUTENBERG.*$", re.M)
_GUTENBERG_END = re.compile(r"^\*\*\* ?END OF (?:THE|THIS) PROJECT GUTENBERG.*$", re.M)
_ILLUSTRATION = re.compile(r"\[Illustration[^\]]*\]", re.S)


@dataclass(frozen=True)
class TextChapter:
    number: int
    title: str
    body: str


def strip_gutenberg(text: str) -> str:
    """The text between Project Gutenberg's START and END markers (all of it if absent)."""
    start = _GUTENBERG_START.search(text)
    end = _GUTENBERG_END.search(text, start.end() if start else 0)
    return text[start.end() if start else 0 : end.start() if end else len(text)]


def unwrap(text: str) -> str:
    """Join hard-wrapped lines inside each paragraph; paragraphs stay blank-line separated.

    Lines that look laid out (indented verse, table rows) are kept as they are.
    """
    paragraphs = re.split(r"\n[ \t]*\n+", text)
    out = []
    for p in paragraphs:
        lines = [line.rstrip() for line in p.split("\n") if line.strip()]
        if not lines:
            continue
        if all(line.startswith((" ", "\t")) for line in lines) and len(lines) > 1:
            out.append("\n".join(line.strip() for line in lines))
        else:
            out.append(" ".join(line.strip() for line in lines))
    return "\n\n".join(out)


def split_chapters(
    text: str, heading: str = DEFAULT_HEADING, title_lines: int = 0
) -> list[TextChapter]:
    """Chapters between headings that start at column 0.

    Indented headings (a table of contents) are ignored. `title_lines` is the number of
    non-blank lines after a heading that belong to the title ("CHAPTER ONE" / "PLAYING
    PILGRIMS"). Text before the first heading (front matter) is dropped.
    """
    text = normalize_body(_ILLUSTRATION.sub("", text))
    marks = list(re.finditer(heading, text, re.M))
    chapters = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        rest = text[m.end() : end].split("\n")
        title_parts = [m.group(0).strip()]
        taken = 0
        while rest and taken < title_lines:
            line = rest.pop(0)
            if line.strip():
                title_parts.append(line.strip())
                taken += 1
        body = normalize_body(unwrap("\n".join(rest)))
        if body:
            title = " ".join(title_parts).rstrip(".]")
            chapters.append(TextChapter(len(chapters) + 1, title, body))
    return chapters
