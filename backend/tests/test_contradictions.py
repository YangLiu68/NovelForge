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


ILSA = CharacterRef("i", "Ilsa Corr")


def test_dead_character_active_after_death_only():
    cast = (MARA, TOMAS)
    [f] = run(
        ["Tomas died of fever in Hollin.", "Tomas was in Varrow that morning."],
        cast=cast,
        days=[10, 20],
    )
    assert f.kind == "dead_character_active" and f.category == "timeline"
    assert [e.value for e in f.evidence] == ["dead", "Varrow"]
    # A flashback set before the death, a memory, and unknown time are not contradictions.
    assert run(["Tomas died in Hollin.", "Tomas was in Varrow."], cast=cast, days=[10, 5]) == []
    assert (
        run(["Tomas died.", "Mara remembered how Tomas was in Varrow."], cast=cast, days=[10, 20])
        == []
    )
    assert run(["Tomas died.", "Tomas was in Varrow."], cast=cast, days=[10, None]) == []


def test_location_needs_travel_time():
    travel = {("Hollin", "Varrow"): 3}
    texts = ["Mara was in Hollin that morning.", "Mara arrived in Varrow."]

    def go(days, travel=travel):
        chapters = [
            ChapterRef(f"c{i}", i, f"Ch {i}", body, 1, day)
            for i, (body, day) in enumerate(zip(texts, days, strict=True), start=1)
        ]
        claims = [c for ch in chapters for c in extract_claims(ch, [MARA])]
        return detect_contradictions(claims, chapters, [MARA], travel=travel)

    [f] = go([0, 1])
    assert f.kind == "location_conflict" and "takes 3 days" in f.explanation
    assert go([0, 3]) == []  # enough time
    assert go([0, 1], travel={}) == []  # unknown travel time: no judgement


def test_ability_used_without_learning():
    [f] = run(["Mara could not swim.", "Mara swam out to the boat."], days=[0, 9])
    assert f.kind == "ability_conflict" and f.predicate == "ability:swim"
    assert (
        run(
            ["Mara could not swim.", "Mara learned to swim.", "Mara swam out to the boat."],
            days=[0, 5, 9],
        )
        == []
    )


def test_explicit_change_starts_a_new_period():
    texts = ["Mara's hair was black.", "That week Mara dyed her hair red.", "Mara's hair was red."]
    assert run(texts, days=[0, 5, 9]) == []
    texts[2] = "Mara's hair was black."
    [f] = run(texts, days=[0, 5, 9])
    assert f.kind == "attribute_conflict" and [e.value for e in f.evidence] == ["red", "black"]


def test_undated_statements_are_ordered_by_chapter_around_a_change():
    # Chapter 1 has no story day; the dye happens in chapter 2. Chapter 1 belongs before it.
    texts = ["Mara's hair was black.", "That week Mara dyed her hair red.", "Mara's hair was red."]
    assert run(texts, days=[None, 5, 9]) == []
