from novelforge.core.text import (
    inside_dialogue,
    normalize_body,
    parse_number,
    sentence_bounds,
    split_passages,
)


def test_normalize_body_is_canonical():
    assert normalize_body("\r\n\nA line.  \r\n\r\nB\n\n") == "A line.\n\nB"
    assert normalize_body(normalize_body("x \n\n y")) == normalize_body("x \n\n y")


def test_split_passages_offsets_slice_the_body():
    body = "First para\nstill first.\n\n  Second para.\n\n\n# Heading\n\nLast"
    spans = split_passages(body)
    assert [s.text for s in spans] == [
        "First para\nstill first.", "Second para.", "# Heading", "Last",
    ]
    for s in spans:
        assert body[s.start:s.end] == s.text


def test_split_passages_empty():
    assert split_passages("") == []
    assert split_passages("\n\n  \n") == []


def test_parse_number():
    assert parse_number("thirty-one") == 31
    assert parse_number("forty") == 40
    assert parse_number("Forty-Six") == 46
    assert parse_number("nineteen") == 19
    assert parse_number("36") == 36
    assert parse_number("eleventy") is None


def test_inside_dialogue_straight_and_curly_quotes():
    text = 'He said, "Mara was there," and left.\n\n“Tomas is here” she said. Tomas ran.'
    assert inside_dialogue(text, text.index("Mara"))
    assert not inside_dialogue(text, text.index("and left"))
    assert inside_dialogue(text, text.index("Tomas is"))
    assert not inside_dialogue(text, text.index("Tomas ran"))


def test_sentence_bounds():
    text = "One sentence. Mara's eyes were grey; she knew it. Next."
    s, e = sentence_bounds(text, text.index("Mara"), text.index("grey") + 4)
    assert text[s:e] == "Mara's eyes were grey; she knew it."
