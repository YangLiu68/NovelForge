import argparse
import json

import pytest

from novelforge.core.contradictions import detect_contradictions
from novelforge.core.domain import ChapterRef, CharacterRef
from novelforge.core.extraction import extract_claims, extractor_for
from novelforge.core.extraction_zh import EXTRACTOR_ZH, day_offset_zh, parse_cn_number

LIN = CharacterRef("l", "林雪棠", ("三小姐",), {"pronouns": "she/her"})
SU = CharacterRef("s", "苏婉", (), {"pronouns": "she/her"})
CHEN = CharacterRef("c", "陈砚", (), {"pronouns": "he/him", "birthplace": "青州"})
GU = CharacterRef("g", "顾明远", ("顾三爷",), {"pronouns": "he/him"})
CAST = [LIN, SU, CHEN, GU]


def chapter(body: str, number: int = 1, day: int | None = 0) -> ChapterRef:
    return ChapterRef(f"c{number}", number, "T", body, 1, day)


def facts(body: str, **kw):
    return [
        (c.subject_id, c.predicate, c.value, c.modality)
        for c in extract_claims(chapter(body, **kw), CAST)
    ]


@pytest.mark.parametrize(
    "raw, n",
    [("十七", 17), ("二十", 20), ("二十三", 23), ("廿三", 23), ("十", 10), ("五十六", 56),
     ("一百零二", 102), ("17", 17), ("七八", None), ("岁", None)],
)  # fmt: skip
def test_chinese_numbers(raw, n):
    assert parse_cn_number(raw) == n


def test_chinese_text_uses_the_chinese_extractor():
    claims = extract_claims(chapter("林雪棠今年十七岁。"), CAST)
    assert [c.extractor for c in claims] == [EXTRACTOR_ZH]
    assert extractor_for("林雪棠今年十七岁。") == EXTRACTOR_ZH
    assert extractor_for("Mara was thirty-one.") == "rules-v6"


def test_each_predicate_next_to_a_name():
    body = (
        "林雪棠今年十七岁。林雪棠的眼睛是琥珀色的。林雪棠一头黑发。陈砚是左撇子。"
        "陈砚生在临江县。顾明远死了。苏婉不会游泳。陈砚学会了骑马。陈砚骑着马走了。"
        "顾三爷回到了雾港。"
    )
    assert facts(body) == [
        ("l", "age", "17", "asserted"),
        ("l", "eye_color", "amber", "asserted"),
        ("l", "hair_color", "black", "asserted"),
        ("c", "handedness", "left", "asserted"),
        ("c", "birthplace", "临江县", "asserted"),
        ("g", "status", "dead", "asserted"),
        ("s", "ability:swim", "cannot", "asserted"),
        ("c", "ability:ride", "learned", "asserted"),
        ("c", "ability:ride", "used", "asserted"),
        ("g", "location", "雾港", "asserted"),
    ]


def test_one_subject_across_clauses():
    body = "林雪棠穿着一件灰色的呢大衣，眼睛却是琥珀色的。苏婉是林家的丫头，今年二十岁，一头乌黑的头发。"
    assert facts(body) == [
        ("l", "eye_color", "amber", "asserted"),  # not the grey of the coat
        ("s", "age", "20", "asserted"),
        ("s", "hair_color", "black", "asserted"),  # 丫头 is in a 是… predicate
    ]


@pytest.mark.parametrize(
    "body",
    [
        "林雪棠的母亲有一双灰色的眼睛。",  # the mother's eyes
        "一头白发的老人拉住了林雪棠。",  # the old man's hair
        "林雪棠看着陈砚的背影，一头黑发的人。",  # another name in between, hair owned by 人
        "林雪棠十七八岁的样子。",  # a range
        "林雪棠十八岁生日那天。",  # a birthday, not an age
        "林雪棠的眼睛红了。",  # crying, not a colour
        "林雪棠差点冻死在雪里。",  # near death
        "顾明远死了丈夫。",  # her husband died
        "林雪棠穿着灰色的大衣，像她过世的母亲。",  # the mother died
        "林雪棠想游到岸边。",  # intention
        "陈砚不会骑马，只好走路。",  # cannot, not a use
        "林雪棠回到了家里。",  # not a place name
        "林雪棠站在钱庄门口。",  # a bank, not a place name
    ],
)
def test_look_alikes_are_not_asserted(body):
    asserted = [f for f in facts(body) if f[3] == "asserted" and f[1] != "ability:ride"]
    assert asserted == [], asserted


@pytest.mark.parametrize(
    "body, modality",
    [
        ("“林雪棠的眼睛是蓝色的。”钱伯说。", "reported"),
        ("灯光底下，林雪棠的眼睛看上去几乎是黑的。", "hedged"),
        ("听说顾明远死了。", "hedged"),
        ("如果林雪棠在苏州，就好了。", "hedged"),
        ("梦里，顾明远死了。", "hedged"),
        ("苏婉十岁那年被卖进林家。", "recalled"),
        ("陈砚十二岁跟着叔叔来到雾港。", "recalled"),  # an age as a time adverbial
        ("林雪棠记得自己一头黑发的样子。", "recalled"),
        ("林雪棠醒来。她死在十九岁那年的腊月。", "recalled"),
        ("林雪棠的头发还像从前一样，是栗色的。", "asserted"),  # a comparison, not a memory
    ],
)
def test_modality(body, modality):
    found = facts(body)
    assert found and {f[3] for f in found} == {modality}, found


def test_pronouns_resolve_only_when_unambiguous():
    # One woman named in the sentence: 她 is 苏婉.
    found = extract_claims(chapter("苏婉推门进来，她的头发还像从前一样，是栗色的。"), CAST)
    assert [(c.subject_id, c.predicate, c.value) for c in found] == [("s", "hair_color", "brown")]
    assert found[0].details["resolved"]["pronoun"] == "她"
    assert found[0].confidence == 0.8
    assert found[0].spans[0].quote.startswith("苏婉")  # the quote starts at the name
    # Two women in the sentence: no guess.
    assert facts("林雪棠把毛巾递给苏婉，她的头发是栗色的。") == []
    # Gender must match the sheet: 他 cannot be 苏婉.
    assert facts("苏婉推门进来，他的头发是栗色的。") == []
    # The previous sentence counts when this one names nobody before the pronoun.
    assert facts("陈砚没有回答。他是左撇子。") == [("c", "handedness", "left", "asserted")]


def test_hair_dye_is_a_change_not_a_contradiction():
    chapters = [
        chapter("林雪棠一头黑发。", 1, 0),
        chapter("林雪棠把头发染成了栗色。", 2, 3),
        chapter("林雪棠栗色的头发剪短了。", 3, 30),
    ]
    claims = [c for ch in chapters for c in extract_claims(ch, CAST)]
    assert [c.details.get("change", False) for c in claims] == [False, True, False]
    assert detect_contradictions(claims, chapters, CAST) == []


def test_detectors_run_on_chinese_claims():
    chapters = [
        chapter("陈砚是左撇子。苏婉不会游泳。顾明远死了。林雪棠今年十七岁。", 1, 0),
        chapter(
            "陈砚惯用右手。陈砚生在临江县。苏婉游到了船边。顾明远回到了雾港。林雪棠二十二岁了。",
            2,
            30,
        ),
    ]
    claims = [c for ch in chapters for c in extract_claims(ch, CAST)]
    findings = detect_contradictions(claims, chapters, CAST)
    kinds = sorted((f.kind, f.subject_name) for f in findings)
    assert kinds == [
        ("ability_conflict", "苏婉"),
        ("age_timeline", "林雪棠"),  # 17 to 22 in 30 days
        ("attribute_conflict", "陈砚"),
        ("canon_conflict", "陈砚"),  # the sheet says 青州
        ("dead_character_active", "顾明远"),
    ]
    # A Chinese novel gets Chinese wording, built from the same values.
    text = {f.kind: (f.explanation, f.suggestion) for f in findings}
    assert (
        text["attribute_conflict"][0]
        == "陈砚的惯用手前后不一致：第 1 章是“左手”；第 2 章是“右手”。"
    )
    assert text["canon_conflict"][0] == "人物卡上陈砚的出生地是“青州”，但第 2 章写的是“临江县”。"
    assert "中间过了 30 天，年龄应该是 17 或 18 岁" in text["age_timeline"][0]
    assert text["ability_conflict"][1].startswith("在第 1 章和第 2 章之间写苏婉学会游泳")


def test_day_offsets():
    body = "三天后，顾明远回到了雾港。第二天，陈砚到了青州。"
    assert day_offset_zh(body, body.index("顾明远")) == 3
    assert day_offset_zh(body, body.index("陈砚")) == 1


def test_dev_sample_scores(capsys):
    """The development sample: every labelled contradiction found, no look-alike reported."""
    from novelforge.cli import cmd_eval_facts, cmd_eval_sample

    cmd_eval_sample(argparse.Namespace(name="wugang-xinzha", db=False, json=True))
    result = json.loads(capsys.readouterr().out)
    assert result["extractor"] == EXTRACTOR_ZH
    assert (result["true_positives"], result["false_positives"]) == (7, 0)
    assert result["negatives_violated"] == 0
    cmd_eval_facts(argparse.Namespace(name="wugang-xinzha", json=True, out=None))
    facts_result = json.loads(capsys.readouterr().out)
    assert facts_result["precision"] == 1.0
    assert facts_result["recall"] >= 0.9


@pytest.mark.parametrize(
    "body, expected",
    [
        ("林雪棠今年十七。", [("l", "age", "17", "asserted")]),
        ("周铁山走了。陈砚今年五十三了。", [("c", "age", "53", "asserted")]),
        ("苏婉不会水。", [("s", "ability:swim", "cannot", "asserted")]),
        ("顾明远不识字。", [("g", "ability:read", "cannot", "asserted")]),
        ("顾明远死了快两年了。", [("g", "status", "dead", "asserted")]),
        ("林雪棠跟着陈砚学会了骑马。", [("l", "ability:ride", "learned", "asserted")]),
        ("陈砚生在江陵。", [("c", "birthplace", "江陵", "asserted")]),
        ("陈砚生在寒冬。", []),
        ("陈砚生在云州城外。", [("c", "birthplace", "云州", "asserted")]),
        ("苏婉的头发已经染得乌黑。", [("s", "hair_color", "black", "asserted")]),
        (
            "顾明远把那封信抖开，借着火把的光一行一行看下去。",
            [("g", "ability:read", "used", "asserted")],
        ),
        ("陈砚骑在一匹通身乌黑的高头大马上。", [("c", "ability:ride", "used", "asserted")]),
        ("陈砚一辈子使的都是右手刀。", [("c", "handedness", "right", "asserted")]),
        ("林雪棠把乌发膏挑在木梳上。", []),
    ],
)
def test_v2_phrasings(body, expected):
    """Phrasings added in rules-zh-v2, after the first held-out sample (BENCHMARK.md section 9)."""
    assert facts(body) == expected


def test_v2_pronouns():
    # A man named next to a woman does not block 她.
    assert facts("林雪棠跟陈砚说完话。她是左撇子。") == [("l", "handedness", "left", "asserted")]
    # A resolved 她 carries over to the next sentence that names nobody.
    assert facts("苏婉不会游泳。她在山里长大。她生在青州。") == [
        ("s", "ability:swim", "cannot", "asserted"),
        ("s", "birthplace", "青州", "asserted"),
    ]
    # Across a paragraph break.
    assert facts("顾明远等在岭上。\n\n他骑在一匹黑马上。") == [
        ("g", "ability:ride", "used", "asserted")
    ]
    # A person noun in between: 她 could be 这姑娘.
    assert facts("林雪棠以为这姑娘娇气，后来才知道，她骑马很稳。") == []
