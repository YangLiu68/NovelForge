from novelforge.core.contradictions import detect_contradictions
from novelforge.core.domain import ChapterRef, CharacterRef
from novelforge.core.extraction import extract_claims

MARA = CharacterRef("m", "Mara Venn")
TOMAS = CharacterRef("t", "Tomas Hale", (), {"birthplace": "Varrow"})


def run(texts, cast=(MARA, TOMAS), days=None, min_confidence=0.6, modalities=("asserted",)):
    days = days or [None] * len(texts)
    chapters = [
        ChapterRef(f"c{i}", i, f"Ch {i}", body, 1, day)
        for i, (body, day) in enumerate(zip(texts, days, strict=True), start=1)
    ]
    claims = [c for ch in chapters for c in extract_claims(ch, list(cast))]
    return detect_contradictions(
        claims,
        chapters,
        list(cast),
        min_confidence=min_confidence,
        modalities=frozenset(modalities),
    )


def test_static_conflict_with_evidence_from_both_sides():
    [f] = run(["Mara's eyes were grey.", "Mara's eyes were green."])
    assert (f.kind, f.severity, f.predicate) == ("attribute_conflict", "high", "eye_color")
    assert [(e.chapter_number, e.value) for e in f.evidence] == [(1, "grey"), (2, "green")]
    assert "chapter 2" in f.suggestion and "'grey'" in f.suggestion


def test_majority_value_is_suggested():
    [f] = run(["Mara's eyes were green.", "Mara's eyes were grey.", "Mara's grey eyes."])
    assert "Make chapter 1 say 'grey'" in f.suggestion


def test_canon_conflict_only_cites_disagreeing_text():
    [f] = run(["Tomas, born in Varrow, swam.", "Tomas was born in Hollin."])
    assert f.kind == "canon_conflict" and f.canon_value == "Varrow"
    assert [e.value for e in f.evidence] == ["Hollin"]


def test_consistent_text_gives_no_findings():
    assert run(["Mara's eyes were grey.", "Mara's grey eyes."]) == []


def test_low_confidence_claims_are_excluded_by_default():
    texts = ["Mara's eyes were grey.", "Mara's eyes seemed green."]
    assert run(texts) == []
    [f] = run(texts, min_confidence=0.3, modalities=("asserted", "hedged"))
    assert f.severity == "medium"  # a hedged claim is involved


def test_age_against_elapsed_story_time():
    ok = run(["Mara was thirty-one.", "Mara was thirty-six."], days=[0, 1827])
    assert ok == []
    birthday = run(["Mara was thirty-one.", "Mara was thirty-two."], days=[0, 3])
    assert birthday == []
    [bad] = run(["Mara was forty.", "Mara was forty-six."], days=[0, 3])
    assert bad.kind == "age_timeline" and "40 or 41" in bad.explanation


def test_age_going_down():
    [f] = run(["Mara was forty.", "Mara was thirty."], days=[0, 400])
    assert "cannot go down" in f.suggestion


def test_age_with_unknown_time_is_not_judged():
    assert run(["Mara was forty.", "Mara was forty-six."], days=[0, None]) == []
