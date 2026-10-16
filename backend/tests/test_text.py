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
        "First para\nstill first.",
        "Second para.",
        "# Heading",
        "Last",
    ]
    for s in spans:
        assert body[s.start : s.end] == s.text


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


def test_chinese_sentences_dialogue_and_tokens():
    from novelforge.core.lang import detect_language, text_length
    from novelforge.core.text import inside_dialogue, sentence_bounds, tokens

    t = "沈知微心里一软，把钱给了他。小乞丐愣住了！“你为什么帮我？”她问。"
    i = t.index("小乞丐")
    assert t[slice(*sentence_bounds(t, i, i + 3))] == "小乞丐愣住了！"
    j = t.index("为什么")
    assert t[slice(*sentence_bounds(t, j, j + 3))] == "“你为什么帮我？”"
    assert inside_dialogue(t, j) and not inside_dialogue(t, i)
    k = "她说：「青雀。」然后走了。"
    assert inside_dialogue(k, k.index("青雀")) and not inside_dialogue(k, k.index("然后"))
    # An ellipsis inside Chinese dialogue does not end the sentence.
    e = "“走投无路的时候……拿着它，去城西……找……”话没说完。"
    assert sentence_bounds(e, 2, 4) == (0, len(e))
    assert tokens("Mara 看见沈知微") == ["mara", "看见", "见沈", "沈知", "知微"]
    assert detect_language("沈知微是冻醒的。") == "zh"
    assert detect_language("Mara was cold. 雪") == "en"
    assert text_length("沈知微是冻醒的。") == (7, "characters")
    assert text_length("Mara was cold.") == (3, "words")


def test_chinese_plain_text_chapters():
    from novelforge.core.plaintext import split_chapters

    raw = (
        "　　第一章　回到十七岁\n　　沈知微是冻醒的。\n　　窗纸破了一角。\n"
        "第二章 三十七文\n　　天刚亮。\n"
    )
    chapters = split_chapters(raw)
    assert [(c.number, c.title) for c in chapters] == [
        (1, "第一章 回到十七岁"),
        (2, "第二章 三十七文"),
    ]
    # Each line is a paragraph; no spaces are inserted between Chinese characters.
    assert chapters[0].body == "沈知微是冻醒的。\n\n窗纸破了一角。"
