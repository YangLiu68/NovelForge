from novelforge.core.domain import ChapterRef, CharacterRef
from novelforge.core.extraction import extract_claims, surface_forms

MARA = CharacterRef("m", "Mara Venn", ("the cartographer",))
TOMAS = CharacterRef("t", "Tomas Hale")
ILSA = CharacterRef("i", "Ilsa Corr", ("the Warden",), {"eye_color": "brown"})
CAST = [MARA, TOMAS, ILSA]


def chapter(body: str, story_day: int | None = 0, version: int = 1) -> ChapterRef:
    return ChapterRef("c1", 1, "T", body, version, story_day)


def facts(body: str, **kw):
    return [
        (c.subject_id, c.predicate, c.value, c.modality)
        for c in extract_claims(chapter(body, **kw), CAST)
    ]


def test_basic_attribute_patterns():
    body = (
        "Mara's grey eyes narrowed. Tomas had hazel eyes. The Warden's eyes were a deep brown. "
        "Tomas was left-handed. Mara Venn was thirty-one. Ilsa, forty-six, sat down. "
        "Tomas was born in Low Hollin. The thirty-six-year-old Mara walked in. "
        "Mara's hair was black."
    )
    assert facts(body) == [
        ("m", "eye_color", "grey", "asserted"),
        ("t", "eye_color", "hazel", "asserted"),
        ("i", "eye_color", "brown", "asserted"),
        ("t", "handedness", "left", "asserted"),
        ("m", "age", "31", "asserted"),
        ("i", "age", "46", "asserted"),
        ("t", "birthplace", "Low Hollin", "asserted"),
        ("m", "age", "36", "asserted"),
        ("m", "hair_color", "black", "asserted"),
    ]


def test_spans_are_exact_slices():
    body = "Rain fell.\n\nAt the window, Mara's eyes were grey as slate."
    claims = extract_claims(chapter(body), CAST)
    assert len(claims) == 1
    span = claims[0].spans[0]
    assert body[span.start : span.end] == span.quote == "Mara's eyes were grey"


def test_alias_sentence_start_capitalised():
    assert facts("The Warden's eyes were brown.") == [("i", "eye_color", "brown", "asserted")]


def test_hedged_and_reported_modalities():
    assert facts("In the fog, Ilsa's eyes seemed almost black.") == [
        ("i", "eye_color", "black", "hedged")
    ]
    assert facts('"Says here Tomas Hale has blue eyes," the clerk said.') == [
        ("t", "eye_color", "blue", "reported")
    ]
    assert facts("Some said Tomas was born in Hollin.") == [("t", "birthplace", "Hollin", "hedged")]


def test_hedge_in_other_clause_does_not_leak():
    assert facts("Mara's eyes were grey; Tomas seemed tired.") == [
        ("m", "eye_color", "grey", "asserted")
    ]


def test_age_trap_is_not_an_age():
    assert facts("Tomas was ten minutes late, which for Tomas was early.") == []


def test_pronouns_and_negation_are_not_extracted():
    # Documented limitation (pronouns) and a guard (negation).
    assert facts("Her eyes were green. Tomas was not left-handed.") == []


def test_word_boundaries():
    assert facts("Marabel's eyes were blue. Tomasz was left-handed.") == []


def test_ambiguous_first_name_is_dropped():
    cast = [CharacterRef("a", "Ann Holt"), CharacterRef("b", "Ann Pike")]
    forms = {f.text for f in surface_forms(cast)}
    assert "Ann" not in forms and {"Ann Holt", "Ann Pike"} <= forms


def test_explicit_alias_beats_implicit_first_name():
    cast = [CharacterRef("a", "Kit Marlowe"), CharacterRef("b", "Kit", ("Kit",))]
    owner = {f.text: f.character.id for f in surface_forms(cast)}
    assert owner["Kit"] == "b"


def test_effective_time_and_uncertainty():
    timed = extract_claims(chapter("Mara's eyes were grey.", story_day=12), CAST)[0]
    assert (timed.effective_day, timed.time_certainty) == (12, "chapter_day")
    unknown = extract_claims(chapter("Mara's eyes were grey.", story_day=None), CAST)[0]
    assert (unknown.effective_day, unknown.time_certainty) == (None, "unknown")


def test_claim_ids_are_deterministic_and_version_scoped():
    a = extract_claims(chapter("Mara's eyes were grey."), CAST)
    b = extract_claims(chapter("Mara's eyes were grey."), CAST)
    c = extract_claims(chapter("Mara's eyes were grey.", version=2), CAST)
    assert [x.id for x in a] == [x.id for x in b]
    assert a[0].id != c[0].id
