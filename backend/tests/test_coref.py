"""rules-v4: pronoun and "with"-phrase attribution, and the cases where it must abstain."""

from novelforge.core.contradictions import detect_contradictions
from novelforge.core.domain import ChapterRef, CharacterRef
from novelforge.core.extraction import extract_claims, surface_forms
from novelforge.core.text import sentence_bounds

MARA = CharacterRef("m", "Mara Venn", (), {"pronouns": "she/her"})
TOMAS = CharacterRef("t", "Tomas Hale", (), {"pronouns": "he/him"})
ILSA = CharacterRef("i", "Ilsa Corr", (), {"pronouns": "she/her"})
KEL = CharacterRef("k", "Kel Dorran")  # no pronouns on the sheet
CAST = [MARA, TOMAS, ILSA, KEL]


def facts(body: str, cast=CAST):
    claims = extract_claims(ChapterRef("c1", 1, "T", body, 1, 0), cast)
    return [(c.subject_id, c.predicate, c.value, c.modality) for c in claims]


def test_possessive_pronoun_in_the_same_sentence():
    claims = extract_claims(
        ChapterRef("c1", 1, "T", "Mara looked up, her grey eyes narrowing.", 1, 0), CAST
    )
    assert [(c.subject_id, c.predicate, c.value, c.modality) for c in claims] == [
        ("m", "eye_color", "grey", "asserted")  # "looked up" is not a perception hedge
    ]
    c = claims[0]
    assert c.spans[0].quote == "Mara looked up, her grey eyes"
    assert c.details["resolved"]["via"] == "pronoun"
    assert c.confidence == 0.8  # resolved facts are a little less certain


def test_subject_pronoun_refers_to_the_previous_sentence():
    body = "Tomas came in from the rain. He had a broken nose and hazel eyes."
    assert facts(body) == [("t", "eye_color", "hazel", "asserted")]


def test_nearest_sentence_decides():
    # Ilsa is two sentences back; the previous sentence names only Mara.
    body = "Ilsa left early. Mara stayed by the fire. She had grey eyes."
    assert facts(body) == [("m", "eye_color", "grey", "asserted")]


def test_two_candidates_of_the_same_gender_abstain():
    assert facts("Mara met Ilsa at the gate. Her eyes were green.") == []


def test_unknown_pronouns_abstain():
    assert facts("Kel looked up, his grey eyes narrowing.") == []


def test_person_noun_between_abstains():
    assert facts("Mara looked at the girl, her blue eyes wide.") == []


def test_dialogue_pronoun_is_not_resolved():
    assert facts('Tomas waited. "Her eyes were green," he said.') == []


def test_they_needs_a_single_person_in_view():
    ash = CharacterRef("a", "Ash Merrow", (), {"pronouns": "they/them"})
    assert facts("Ash pushed their red hair back.", [ash, MARA]) == [
        ("a", "hair_color", "red", "asserted")
    ]
    assert facts("Ash spoke to Mara. Their eyes were blue.", [ash, MARA]) == []


def test_with_phrase_belongs_to_the_sentence_subject():
    assert facts("Tomas was a grave, silent young man, with handsome brown eyes.") == [
        ("t", "eye_color", "brown", "asserted")
    ]
    body = "Lying on the grass, Tomas began the story, with the brown eyes on the river."
    assert facts(body) == [("t", "eye_color", "brown", "asserted")]
    # Another person in between: the eyes may be theirs.
    assert facts("Mara sat with the girl with blue eyes.") == []
    assert facts("Mara talked to Ilsa, with grey eyes fixed on the door.") == []


def test_feature_list_after_a_possessive():
    body = "Ilsa came in. She consoled herself with her fair complexion, keen blue eyes, and curls."
    assert ("i", "eye_color", "blue", "asserted") in facts(body)
    # "his" starts another owner, and nobody he could be is in view.
    assert facts("Mara covered her face and his blue eyes.") == []


def test_ages_in_apposition_and_capitalised_numbers():
    assert facts("Mara, the eldest of the four, was sixteen, and very pretty.") == [
        ("m", "age", "16", "asserted")
    ]
    assert facts("Fifteen-year-old Tomas was very tall.") == [("t", "age", "15", "asserted")]
    assert facts("Ilsa, or Ils, as everyone called her, was a rosy girl of thirteen.") == [
        ("i", "age", "13", "asserted")
    ]


def test_sailing_as_travel_and_negated_use():
    assert facts("Mara sailed away to find the Old World.") == []
    assert facts("Mara sailed the skiff across the bay.") == [
        ("m", "ability:sail", "used", "asserted")
    ]
    assert facts("Tomas wrote no more stories.") == []


def test_perception_hedges_only_what_it_governs():
    assert facts("Mara read as if alone.") == [("m", "ability:read", "used", "asserted")]
    assert facts("Mara's eyes seemed almost green.") == [("m", "eye_color", "green", "hedged")]
    assert facts("If Tomas was in Varrow, nobody saw him.") == [
        ("t", "location", "Varrow", "hedged")
    ]


def test_titles_are_never_implicit_aliases():
    cast = [CharacterRef("s", "Miss Stacy"), CharacterRef("b", "Lady Catherine de Bourgh")]
    forms = {f.text for f in surface_forms(cast)}
    assert "Miss" not in forms and "Lady" not in forms


def test_title_full_stop_does_not_end_a_sentence():
    text = "Jo laughed. Mrs. March smiled at Dr. Venn! Then she left."
    assert text[slice(*sentence_bounds(text, 14, 15))] == "Mrs. March smiled at Dr. Venn!"


def test_pronouns_inferred_from_the_chapter():
    kel = CharacterRef("k", "Kel Dorran")
    body = (
        "Kel laughed as he climbed the stairs. Kel said he would wait. "
        "Kel looked up, his grey eyes narrowing."
    )
    assert facts(body, [kel]) == [("k", "eye_color", "grey", "asserted")]
    # One vote is not enough.
    assert facts("Kel looked up, his grey eyes narrowing.", [kel]) == []


def test_colour_words_for_one_colour_do_not_conflict():
    def report(a: str, b: str):
        chapters = [
            ChapterRef("c1", 1, "One", f"Mara's hair was {a}.", 1, None),
            ChapterRef("c2", 2, "Two", f"Mara's hair was {b}.", 1, None),
        ]
        claims = [c for ch in chapters for c in extract_claims(ch, [MARA])]
        return [f.kind for f in detect_contradictions(claims, chapters, [MARA])]

    assert report("golden", "yellow") == []
    assert report("blond", "golden") == []
    assert report("auburn", "red") == ["attribute_conflict"]
