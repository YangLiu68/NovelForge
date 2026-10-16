"""Which language a text is in, as far as NovelForge cares: Chinese or not (English).

The rule-based extractor and the English full-text index only understand English; Chinese
novels get Chinese sentence and dialogue handling, bigram tokens, Chinese chapter headings and
Chinese prompts for the LLM stages.
"""

import re

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> str:
    """'zh' when Chinese characters outnumber Latin letters (sampled), else 'en'."""
    sample = text[:20000]
    cjk = len(_CJK.findall(sample))
    latin = len(_LATIN.findall(sample))
    return "zh" if cjk and cjk >= latin / 2 else "en"


def is_chinese(text: str) -> bool:
    return detect_language(text) == "zh"


def text_length(text: str) -> tuple[int, str]:
    """(count, unit): Chinese characters for Chinese text, words otherwise."""
    if is_chinese(text):
        return len(_CJK.findall(text)), "characters"
    return len(text.split()), "words"
