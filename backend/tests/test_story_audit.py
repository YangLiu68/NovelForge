# ruff: noqa: E501  (scripted model answers read better unwrapped)
"""Story-logic audit: every deterministic check, on a tiny Chinese story with scripted answers.

The model is the offline mock answering by schema; what is tested is what the code does with the
answers (quote location, name resolution, citation rules, verdict downgrades, delayed reveals,
plot references, pacing, plan targets) and the scorer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from novelforge.bench.story_eval import grounding, sample_inputs
from novelforge.core.domain import ChapterRef
from novelforge.core.sample import load_folder
from novelforge.llm.mock import MockLLM
from novelforge.narrative.audit import CastMember, audit_story
from novelforge.narrative.score import score

CH1 = (
    "林晚是被冻醒的。前世她死在二十岁那年的冬天。\n\n"
    "她摸了摸枕头底下，只剩十文钱。她告诉自己：这一世每一文钱都要算清楚。\n\n"
    "母亲留下一枚铜钥匙，说将来会用得上。"
)
CH2 = (
    "林晚在街口遇见一个乞丐，心里一软，把十文钱全给了他。\n\n"
    "堂妹林珠把她推下了台阶，就是看她不顺眼。\n\n"
    "掌柜周伯借给林晚一两银子，不要利息。\n\n"
    "林晚走后，周伯关上门，低声对伙计说：暗柜的密码是梅花，别告诉任何人。"
)
CH3 = (
    "周伯说出了实情：十年前林晚的母亲救过他的命。\n\n"
    "林晚打开了周伯的暗柜，她从没听人说过暗柜的密码。\n\n"
    "两人喝了一碗茶，天就黑了。"
)

CAST = [
    CastMember("林晚", ("晚晚",), "女主，重生。冷静，凡事先算账。"),
    CastMember("林珠", (), "林晚的堂妹。"),
    CastMember("周伯", ("掌柜",), ""),
]


def chapters() -> list[ChapterRef]:
    return [
        ChapterRef("c1", 1, "重生", CH1, 1),
        ChapterRef("c2", 2, "十文钱", CH2, 1),
        ChapterRef("c3", 3, "暗柜", CH3, 1),
    ]


def chapter_of(prompt: str) -> int:
    return int(re.search(r"第 (\d+) 章", prompt).group(1))


NOTES = {
    1: [
        {
            "character": "林晚",
            "kind": "background",
            "text": "前世二十岁冻死",
            "quote": "前世她死在二十岁那年的冬天。",
        },
        # half-width punctuation still locates
        {
            "character": "林晚",
            "kind": "situation",
            "text": "只剩十文钱",
            "quote": "她摸了摸枕头底下,只剩十文钱。",
        },
        {
            "character": "林晚",
            "kind": "personality",
            "text": "每一文钱都算清楚",
            "quote": "这一世每一文钱都要算清楚",
        },
        {"character": "王五", "kind": "goal", "text": "不在名单", "quote": "林晚是被冻醒的。"},
        {
            "character": "林晚",
            "kind": "goal",
            "text": "编造的引文",
            "quote": "她决定去京城找父亲的旧友。",
        },
    ],
    # Read off the act itself: may not be cited as its motive.
    2: [
        {
            "character": "林晚",
            "kind": "personality",
            "text": "心地善良",
            "quote": "心里一软，把十文钱全给了他",
        }
    ],
    3: [
        {
            "character": "周伯",
            "kind": "relationship",
            "text": "林晚的母亲救过他的命",
            "quote": "十年前林晚的母亲救过他的命。",
        },
        {
            "character": "林晚",
            "kind": "knowledge",
            "text": "她不知道暗柜密码",
            "quote": "她从没听人说过暗柜的密码",
        },
    ],
}

BEATS = {
    1: {
        "summary": "林晚重生，清点家底。",
        "tension": 3,
        "emotions": ["suspense"],
        "hook": {"present": True, "quote": "母亲留下一枚铜钥匙，说将来会用得上。"},
        "beats": [],
        "setups": [{"key": "铜钥匙", "text": "母亲留下的铜钥匙", "quote": "母亲留下一枚铜钥匙"}],
    },
    2: {
        "summary": "林晚施舍乞丐，被堂妹推下台阶，掌柜借钱。",
        "tension": 3,
        "emotions": ["anger"],
        # The hook quote is from the first paragraph: not at the end of the chapter.
        "hook": {"present": True, "quote": "林晚在街口遇见一个乞丐"},
        "beats": [
            {
                "character": "晚晚",
                "action": "把十文钱全给了乞丐",
                "quote": "心里一软，把十文钱全给了他",
                "hostile": False,
                "target": "乞丐",
                "cost": "全部积蓄",
            },
            {
                "character": "林珠",
                "action": "把林晚推下台阶",
                "quote": "堂妹林珠把她推下了台阶",
                "hostile": True,
                "target": "林晚",
                "cost": "",
            },
            {
                "character": "掌柜",
                "action": "无息借钱给林晚",
                "quote": "掌柜周伯借给林晚一两银子，不要利息。",
                "hostile": False,
                "target": "林晚",
                "cost": "一两银子",
                "resolves_crisis": True,
            },
            {
                "character": "乞丐",
                "action": "收下了钱",
                "quote": "遇见一个乞丐",
                "hostile": False,
                "target": "",
                "cost": "",
            },
            {
                "character": "林晚",
                "action": "编造",
                "quote": "林晚骑马去了京城",
                "hostile": False,
                "target": "",
                "cost": "",
            },
        ],
        "setups": [],
    },
    3: {
        "summary": "周伯说出旧恩，林晚打开暗柜。",
        "tension": 1,
        "emotions": ["calm"],
        "hook": {"present": False, "quote": ""},
        "beats": [
            {
                "character": "林晚",
                "action": "打开了暗柜",
                "quote": "林晚打开了周伯的暗柜",
                "hostile": False,
                "target": "",
                "cost": "",
                "uses_secret": True,
                "secret": "暗柜的密码是梅花",
            },
        ],
        "setups": [],
    },
}


def circular_note(prompt: str) -> str:
    return re.search(r"(N\d+)（第 2 章·性格）心地善良", prompt).group(1)


def motive_answer(prompt: str) -> dict:
    """Answers to the motive sub-questions for one beat (the verdict is computed in code)."""
    bid, who, action = re.search(r"(B\d+)（第 \d+ 章）(\S+?)：(.*)", prompt).groups()
    if who == "林晚" and "乞丐" in action:
        # Against the sheet note N2; a reason note that quotes the act; a note never shown.
        return {
            "is_choice": True,
            "reason": "同情",
            "reason_notes": [circular_note(prompt)],
            "against": "人设凡事先算账",
            "against_notes": ["N2", "N99"],
            "explanation": "与人设冲突",
            "severity": 3,
            "fixes": ["补一段前史"],
        }
    if who == "林珠":
        # Dislike is not a reason: harming someone without one is villainy for its own sake.
        return {
            "is_choice": True,
            "reason": "就是看她不顺眼",
            "reason_notes": [],
            "against": "",
            "against_notes": [],
            "explanation": "没有动机",
            "severity": 3,
            "fixes": ["给她一个利益冲突"],
        }
    if who == "周伯":
        return {
            "is_choice": True,
            "reason": "",
            "reason_notes": [],
            "against": "",
            "against_notes": [],
            "explanation": "冷面掌柜却无息借钱",
            "severity": 2,
            "fixes": [],
        }
    # 林晚 opening the safe: a reason stated, cited with an ID that does not exist.
    return {
        "is_choice": True,
        "reason": "想要地契",
        "reason_notes": ["N77"],
        "against": "",
        "against_notes": [],
        "explanation": "合理",
        "severity": 1,
        "fixes": [],
    }


def later_answer(prompt: str) -> dict:
    if "周伯" in prompt:
        nid = re.search(r"(N\d+)（第 3 章", prompt).group(1)
        return {"explained_by": nid, "why": "旧恩"}
    return {"explained_by": "N1", "why": "不是后文的条目"}


def plot_answer(prompt: str) -> dict:
    """The whole-story call only covers causality now; other kinds have their own checks."""
    beat = re.search(r"(B\d+)（第 3 章）林晚：打开了暗柜", prompt).group(1)
    return {
        "issues": [
            {
                "kind": "causality",
                "chapter": 3,
                "character": "",
                "refs": [beat],
                "explanation": "只有果没有因",
                "severity": 2,
                "fixes": [],
            },
            {
                "kind": "knowledge_leak",
                "chapter": 3,
                "character": "林晚",
                "refs": [beat],
                "explanation": "这一类由逐个行为的信息来源检查负责",
                "severity": 3,
                "fixes": [],
            },
        ]
    }


def leak_answer(prompt: str) -> dict:
    # Nothing tells 林晚 the combination; a quote from later in the chapter would not count.
    return {"how": "none", "source": "", "source_notes": [], "source_quote": "两人喝了一碗茶"}


def payoff_answer(prompt: str) -> dict:
    return {"paid_off_by": "", "why": ""}  # the copper key is never used


def rescue_answer(prompt: str) -> dict:
    if "周伯" in prompt:
        return {"deus_ex_machina": True, "why": "从未出场的掌柜突然解围", "fixes": ["提前埋下周伯"]}
    return {"deus_ex_machina": False, "why": "", "fixes": []}


def plan_answer(prompt: str) -> dict:
    first = re.search(r"(I\d+)", prompt.split("\n\n")[-1]).group(1)
    return {
        "suggestions": [
            {
                "targets": [first],
                "chapter": 2,
                "technique": "setup",
                "change": "在第 1 章补一段她讨过饭的经历",
                "why": "让施舍有来由",
                "sample": "",
            },
            {
                "targets": ["I99"],
                "chapter": 2,
                "technique": "reversal",
                "change": "无效目标",
                "why": "",
                "sample": "",
            },
        ]
    }


@pytest.fixture
def mock() -> MockLLM:
    llm = MockLLM()
    llm.on_schema("character_notes", lambda s, p, _: {"notes": NOTES[chapter_of(p)]})
    llm.on_schema("chapter_beats", lambda s, p, _: BEATS[chapter_of(p)])
    llm.on_schema("chapter_shape", lambda s, p, _: BEATS[chapter_of(p)])
    llm.on_schema("knowledge_source", lambda s, p, _: leak_answer(p))
    llm.on_schema("motive_check", lambda s, p, _: motive_answer(p))
    llm.on_schema("later_explanation", lambda s, p, _: later_answer(p))
    llm.on_schema("plot_check", lambda s, p, _: plot_answer(p))
    llm.on_schema("setup_payoff", lambda s, p, _: payoff_answer(p))
    llm.on_schema("rescue_check", lambda s, p, _: rescue_answer(p))
    llm.on_schema("revision_plan", lambda s, p, _: plan_answer(p))
    return llm


def test_notes_are_grounded_and_sheet_notes_come_from_the_description(mock):
    a = audit_story(chapters(), CAST, mock)
    sheet = [n for n in a.notes if n.chapter is None]
    assert [n.text for n in sheet] == ["女主，重生。", "冷静，凡事先算账。", "林晚的堂妹。"]
    text = [n for n in a.notes if n.chapter == 1]
    assert [n.kind for n in text] == ["background", "situation", "personality"]
    for n in text:
        assert CH1[n.start : n.end] == n.quote  # the stored span is always the author's text
    assert {n.located for n in text} >= {"exact", "normalized"}
    reasons = {r["reason"] for r in a.rejected if r["stage"] == "notes"}
    assert reasons == {"character not in the cast", "quote not found in the chapter"}


def test_beats_resolve_aliases_and_keep_unlisted_people_out_of_motive_checks(mock):
    a = audit_story(chapters(), CAST, mock)
    ch2 = [b for b in a.beats if b.chapter == 2]
    assert [(b.character, b.listed) for b in ch2] == [
        ("林晚", True),
        ("林珠", True),
        ("周伯", True),
        ("乞丐", False),
    ]
    judged = {j.beat for j in a.judgements}
    assert all(b.id in judged for b in a.beats if b.listed)
    assert not any(b.id in judged for b in a.beats if not b.listed)
    assert any(r["reason"] == "quote not found in the chapter" for r in a.rejected)


def test_verdict_checks(mock):
    a = audit_story(chapters(), CAST, mock)
    by_actor = {a.beat(j.beat).character + str(a.beat(j.beat).chapter): j for j in a.judgements}
    beggar = by_actor["林晚2"]
    assert beggar.verdict == "contradicts"  # it names a real conflicting note
    assert [c["note"] for c in beggar.conflicts] == ["N2"]
    assert any("N99" in c for c in beggar.checks)
    assert beggar.motives[0]["support"] == []  # the circular note was dropped
    assert any("circular" in c for c in beggar.checks)
    push = by_actor["林珠2"]
    assert push.verdict == "malice_without_cause" and push.fixes
    safe = by_actor["林晚3"]
    assert safe.model_verdict == "consistent" and safe.verdict == "unverified"


def test_a_later_reveal_turns_a_problem_into_a_delayed_explanation(mock):
    a = audit_story(chapters(), CAST, mock)
    loan = next(j for j in a.judgements if a.beat(j.beat).character == "周伯")
    assert loan.model_verdict == "unmotivated"
    assert loan.verdict == "delayed"
    note = next(n for n in a.notes if n.id == loan.explained_by)
    assert note.chapter == 3 and "救过他的命" in note.quote
    # The beggar beat was "explained" by N1, which is not a later note: it stays a problem.
    beggar = next(j for j in a.judgements if "乞丐" in a.beat(j.beat).action)
    assert beggar.verdict == "contradicts"
    assert any("not a later note" in c for c in beggar.checks)


def test_plot_issues_need_valid_references(mock):
    a = audit_story(chapters(), CAST, mock)
    plot = [i for i in a.issues if i.family == "plot"]
    assert sorted((i.kind, i.chapter) for i in plot) == [
        ("dangling_setup", 1),  # its payoff check found nothing later
        ("deus_ex_machina", 2),  # 周伯 resolves a crisis in his first appearance
        ("knowledge_leak", 3),
    ]
    leak = next(i for i in plot if i.kind == "knowledge_leak")
    assert leak.chapter == 3 and leak.character == "林晚"  # anchored on the cited beat
    assert any(e.role == "beat" and e.chapter == 3 for e in leak.evidence)
    rescue = next(i for i in plot if i.kind == "deus_ex_machina")
    assert rescue.character == "周伯" and rescue.severity == 3 and rescue.fixes
    reasons = {r["reason"] for r in a.rejected if r["stage"] == "plot"}
    assert reasons == {"bad kind", "causality without a cause and an effect"}


def test_a_rescuer_seen_earlier_is_not_a_deus_ex_machina(mock):
    early = [
        ChapterRef("c1", 1, "重生", CH1 + "\n\n街口当铺的掌柜周伯是个冷面人。", 1),
        *chapters()[1:],
    ]
    a = audit_story(early, CAST, mock)
    assert not [i for i in a.issues if i.kind == "deus_ex_machina"]
    assert a.usage["calls_by_stage"].get("rescue") is None  # no call was needed


def test_pacing_and_hooks(mock):
    a = audit_story(chapters(), CAST, mock)
    pulses = {p.chapter: p for p in a.pulses}
    assert pulses[1].hook and CH1[pulses[1].hook_start : pulses[1].hook_end].startswith("母亲")
    assert not pulses[2].hook  # its "hook" was the first paragraph
    assert any(r["reason"] == "hook is not at the chapter's end" for r in a.rejected)
    assert pulses[3].tension == 1
    flat = [i for i in a.issues if i.kind == "flat_stretch"]
    assert [i.chapters for i in flat] == [[3]]
    # A quiet ending is a suggestion (add a cliffhanger), not a problem; the flat chapter and
    # the last one get none.
    assert not [i for i in a.issues if i.kind == "no_hook"]
    hooks = [x for x in a.suggestions if x.technique == "cliffhanger" and not x.targets]
    assert [x.chapter for x in hooks] == [2] and "第 2 章" in hooks[0].change


def test_issues_are_ranked_and_the_plan_only_targets_known_issues(mock):
    a = audit_story(chapters(), CAST, mock)
    sev = [i.severity for i in a.issues]
    assert sev == sorted(sev, reverse=True)
    assert a.issues[0].severity == 3 and a.issues[0].family == "character"
    assert [s.targets for s in a.suggestions if s.targets] == [[a.issues[0].id]]
    assert any(r["stage"] == "plan" for r in a.rejected)
    # notes, beats, shape, motives (one per listed beat), leak, later, plot, rescue, payoff (the
    # setup's key word never comes back, so the model is asked), plan
    assert a.usage["calls"] == 3 + 3 + 3 + 4 + 1 + 2 + 1 + 1 + 1 + 1
    g = grounding(a)
    assert g["verdicts_changed_by_checks"] == {
        "consistent -> contradicts": 1,  # its only reason quoted the act itself
        "unverified -> malice_without_cause": 1,  # "看她不顺眼" is not a reason
        "consistent -> unverified": 1,  # the cited note does not exist
        "unmotivated -> delayed": 1,  # explained in chapter 3
    }


def test_model_failures_are_recorded_not_fatal():
    llm = MockLLM()
    llm.on_schema("character_notes", lambda s, p, _: "not json")
    llm.on_schema("chapter_beats", lambda s, p, _: BEATS[chapter_of(p)])
    a = audit_story(chapters(), CAST, llm)
    assert any("not a JSON object" in e for e in a.errors)
    assert any("no judgement" in e for e in a.errors)  # the mock gives empty motive answers
    assert a.beats


def test_scoring_against_labels(mock):
    a = audit_story(chapters(), CAST, mock)
    truth = {
        "problems": [
            {
                "id": "P1",
                "kind": "character",
                "accept": ["contradicts", "unmotivated"],
                "character": "林晚",
                "chapter": 2,
                "evidence": [{"chapter": 2, "text": "把十文钱全给了他"}],
            },
            {
                "id": "P2",
                "kind": "plot",
                "accept": ["knowledge_leak"],
                "character": "林晚",
                "chapter": 3,
                "evidence": [{"chapter": 3, "text": "林晚打开了周伯的暗柜"}],
            },
            {
                "id": "P3",
                "kind": "pacing",
                "accept": ["flat_stretch"],
                "chapter": 2,
                "evidence": [{"chapter": 2, "text": "不要利息"}],
            },
        ],
        "traps": [
            {
                "id": "T1",
                "character": "周伯",
                "chapter": 2,
                "evidence": [{"chapter": 2, "text": "掌柜周伯借给林晚一两银子"}],
            },
            {
                "id": "T2",
                "character": "林珠",
                "chapter": 2,
                "evidence": [{"chapter": 2, "text": "就是看她不顺眼"}],
            },
        ],
    }
    s = score(a, truth, chapters())
    assert [p["found"] for p in s["problem_rows"]] == [True, True, False]
    assert [t["set_off"] for t in s["trap_rows"]] == [False, True]
    assert s["trap_rows"][0]["verdicts"] == ["delayed"]
    assert s["problems_found"] == 2 and s["traps_set_off"] == 1


def test_the_chinese_sample_and_its_labels_load():
    folder = Path(__file__).resolve().parents[2] / "samples" / "xueye-dangpu"
    novel = load_folder(folder)
    chs, cast = sample_inputs(novel)
    assert len(chs) == 8 and cast[0].name == "沈知微" and "利益" in cast[0].description
    import yaml

    truth = yaml.safe_load((folder / "narrative_truth.yaml").read_text(encoding="utf-8"))
    by_number = {c.number: c.body for c in chs}
    for item in truth["problems"] + truth["traps"]:
        for e in item["evidence"]:
            assert e["text"] in by_number[e["chapter"]], (item["id"], e["text"])
    # An audit with no findings scores 0 found and 0 traps set off.
    empty = audit_story(chs, cast, MockLLM())
    s = score(empty, truth, chs)
    assert s["problems_found"] == 0 and s["traps_set_off"] == 0


@pytest.mark.parametrize(
    "name", ["xueye-dangpu", "qingshi-du", "xueye-dangpu-revised", "qingya-wenjian"]
)
def test_every_story_label_quotes_its_chapter(name):
    import yaml

    folder = Path(__file__).resolve().parents[2] / "samples" / name
    chs, _ = sample_inputs(load_folder(folder))
    truth = yaml.safe_load((folder / "narrative_truth.yaml").read_text(encoding="utf-8"))
    by_number = {c.number: c.body for c in chs}
    items = truth["problems"] + truth["traps"] + (truth.get("ambiguous") or [])
    assert len({i["id"] for i in items}) == len(items)
    for item in items:
        for e in item["evidence"]:
            assert e["text"] in by_number[e["chapter"]], (name, item["id"], e["text"])


def test_quotes_stitched_from_several_sentences_keep_the_real_one():
    from novelforge.extraction.verify import locate_sentence

    body = "天刚亮，她出了门。\n\n沈知微心里一软，把二十文全倒进了他的碗里。"
    stitched = "天刚亮，她出了门。沈知微心里一软，把二十文全倒进了他的碗里。"
    loc = locate_sentence(body, stitched)
    assert loc.method == "piece"
    assert body[loc.start : loc.end] == "沈知微心里一软，把二十文全倒进了他的碗里。"
    assert locate_sentence(body, "她骑马去了京城，再也没有回来。") is None


def test_an_empty_or_failed_motive_answer_is_no_judgement(mock):
    def flaky(system, prompt, schema):
        return {} if "林珠" in prompt.split("\n", 1)[0] else motive_answer(prompt)

    mock.on_schema("motive_check", flaky)
    a = audit_story(chapters(), CAST, mock)
    push = next(b for b in a.beats if b.character == "林珠")
    assert push.id not in {j.beat for j in a.judgements}
    assert f"motives: no judgement for {push.id}" in a.errors
    assert len(a.judgements) == 3  # the other beats are still judged


def test_dislike_is_not_a_motive_even_when_a_note_says_so(mock):
    notes2 = list(NOTES[2])
    NOTES[2] = [
        *notes2,
        {"character": "林珠", "kind": "wound", "text": "看堂姐不顺眼", "quote": "就是看她不顺眼"},
    ]

    def cites_dislike(system, prompt, schema):
        if "林珠" not in prompt.split("\n", 1)[0]:
            return motive_answer(prompt)
        nid = re.search(r"(N\d+)（第 2 章·创伤）看堂姐不顺眼", prompt).group(1)
        return {**motive_answer(prompt), "reason": "嫉妒", "reason_notes": [nid]}

    try:
        mock.on_schema("motive_check", cites_dislike)
        a = audit_story(chapters(), CAST, mock)
    finally:
        NOTES[2] = notes2
    push = next(j for j in a.judgements if a.beat(j.beat).character == "林珠")
    assert push.model_verdict == "consistent" and push.verdict == "unverified"
    assert any("dislike or whim" in c for c in push.checks)


def test_a_later_note_must_speak_to_the_beat(mock):
    def unrelated(system, prompt, schema):
        if "周伯" in prompt:
            # A later fact about 周伯 that names neither 林晚 (the target) nor the loan.
            return {"explained_by": re.search(r"(N\d+)（第 3 章", prompt).group(1), "why": "?"}
        return {"explained_by": "", "why": ""}

    notes3 = list(NOTES[3])
    NOTES[3] = [
        {
            "character": "周伯",
            "kind": "background",
            "text": "年轻时在码头扛过活",
            "quote": "两人喝了一碗茶",
        },
        *notes3,
    ]
    try:
        mock.on_schema("later_explanation", unrelated)
        a = audit_story(chapters(), CAST, mock)
    finally:
        NOTES[3] = notes3
    loan = next(j for j in a.judgements if a.beat(j.beat).character == "周伯")
    assert loan.verdict == "unmotivated" and loan.explained_by is None
    assert any("names neither" in c for c in loan.checks)


def test_plot_and_pacing_traps_and_ambiguous_labels(mock):
    a = audit_story(chapters(), CAST, mock)
    truth = {
        "problems": [],
        "traps": [
            # The fixture reports a dangling setup in chapter 1 and a flat chapter 3.
            {
                "id": "R1",
                "kind": "plot",
                "forbid": ["dangling_setup"],
                "chapter": 1,
                "evidence": [{"chapter": 1, "text": "铜钥匙"}],
            },
            {
                "id": "R2",
                "kind": "plot",
                "forbid": ["deus_ex_machina"],
                "chapter": 3,
                "evidence": [{"chapter": 3, "text": "暗柜"}],
            },
            {
                "id": "R3",
                "kind": "pacing",
                "chapter": 3,
                "evidence": [{"chapter": 3, "text": "天就黑了"}],
            },
        ],
        "ambiguous": [
            {
                "id": "Z1",
                "kind": "knowledge",
                "character": "林晚",
                "chapter": 3,
                "evidence": [{"chapter": 3, "text": "林晚打开了周伯的暗柜"}],
            },
        ],
    }
    s = score(a, truth, chapters())
    assert [t["set_off"] for t in s["trap_rows"]] == [True, False, True]
    assert s["ambiguous_rows"] == [
        {
            "id": "Z1",
            "flagged": True,
            "issues": [i.id for i in a.issues if i.kind == "knowledge_leak"],
        }
    ]
    assert s["recall"] is None and s["problems"] == 0
    # Issues on a trap or an ambiguous label are not "unlabelled".
    on_labels = {h for row in s["trap_rows"] + s["ambiguous_rows"] for h in row["issues"]}
    assert not on_labels & set(s["unlabelled_issues"])


def test_long_novels_are_checked_in_windows_and_setups_without_a_key_ask_the_model(mock):
    from novelforge.narrative.audit import StoryAuditor

    windows, payoffs = [], []

    def windowed_plot(system, prompt, schema):
        windows.append(sorted(set(re.findall(r"（第 (\d+) 章）", prompt.split("\n\n")[0]))))
        return {"issues": []}

    def keyless_shape(system, prompt, schema):
        shape = dict(BEATS[chapter_of(prompt)])
        shape["setups"] = [{**x, "key": ""} for x in shape["setups"]]
        return shape

    def payoff(system, prompt, schema):
        payoffs.append(prompt)
        return {"paid_off_by": "", "why": ""}

    mock.on_schema("plot_check", windowed_plot)
    mock.on_schema("chapter_shape", keyless_shape)
    mock.on_schema("setup_payoff", payoff)
    a = StoryAuditor(chapters(), CAST, mock, plot_window=2).run()
    # whole chapters, at most two beats unless one chapter has more
    assert windows == [["2"], ["3"]]
    assert len(payoffs) == 2  # the keyless chapter-1 setup checked against both later windows
    kinds = sorted((i.kind, i.chapter) for i in a.issues if i.family == "plot")
    assert kinds == [("dangling_setup", 1), ("deus_ex_machina", 2), ("knowledge_leak", 3)]
    dangling = next(i for i in a.issues if i.kind == "dangling_setup")
    assert [e.role for e in dangling.evidence] == ["setup"]

    # A setup the model says is paid off in a later window is not dangling.
    mock.on_schema(
        "setup_payoff",
        lambda s, p, _: {"paid_off_by": re.findall(r"(B\d+)（", p)[-1], "why": "用上了"},
    )
    b = StoryAuditor(chapters(), CAST, mock, plot_window=2).run()
    assert not [i for i in b.issues if i.kind == "dangling_setup"]


def test_a_setup_whose_key_comes_back_later_is_paid_off(mock):
    later = [
        *chapters()[:2],
        ChapterRef("c3", 3, "暗柜", CH3 + "\n\n她用那枚铜钥匙打开了箱子。", 1),
    ]
    a = audit_story(later, CAST, mock)
    assert not [i for i in a.issues if i.kind == "dangling_setup"]
    assert "payoff" not in a.usage["calls_by_stage"]  # decided by the key word, no model call
    # A key that is not a word of its chapter is dropped (and the model is asked instead).
    mock.on_schema(
        "chapter_shape",
        lambda s, p, _: {
            **BEATS[chapter_of(p)],
            "setups": [{"key": "金钥匙", "text": "x", "quote": "母亲留下一枚铜钥匙"}]
            if chapter_of(p) == 1
            else [],
        },
    )
    mock.on_schema("setup_payoff", lambda s, p, _: {"paid_off_by": "", "why": ""})
    b = audit_story(later, CAST, mock)
    assert any(r["reason"] == "setup key is not a word of the chapter" for r in b.rejected)
    assert b.usage["calls_by_stage"]["payoff"] == 1


def test_a_secret_with_a_source_is_not_a_leak(mock):
    def told(system, prompt, schema):
        return {
            "how": "told",
            "source": "周伯告诉她",
            "source_notes": [],
            "source_quote": "周伯说出了实情",
        }

    mock.on_schema("knowledge_source", told)
    a = audit_story(chapters(), CAST, mock)
    assert not [i for i in a.issues if i.kind == "knowledge_leak"]
    # "how" without a citation or an earlier quote is not enough.
    mock.on_schema(
        "knowledge_source",
        lambda s, p, _: {
            "how": "past_life",
            "source": "前世",
            "source_notes": [],
            "source_quote": "",
        },
    )
    b = audit_story(chapters(), CAST, mock)
    assert [i.chapter for i in b.issues if i.kind == "knowledge_leak"] == [3]


def test_names_and_ids_from_free_form_model_output():
    from novelforge.narrative.audit import StoryAuditor, _ids

    auditor = StoryAuditor(chapters(), CAST, MockLLM())
    assert auditor.resolve("晚晚") == "林晚"
    assert auditor.resolve("林晚（女主）") == "林晚"
    assert auditor.resolve("林晚的母亲") is None  # someone else, named through 林晚
    assert auditor.resolve("掌柜周伯") == "周伯"
    assert auditor.resolve("路人") is None
    assert _ids("B5（第 2 章）", "B") == ["B5"]
    assert _ids(["B3、B4", "N2", "B3"], "BSN") == ["B3", "B4", "N2"]
    assert _ids("ABS1", "S") == [] and _ids(None, "N") == []


def test_only_information_set_down_earlier_can_leak(mock):
    from novelforge.narrative.audit import StoryAuditor

    auditor = StoryAuditor(chapters(), CAST, mock)
    beat = lambda secret, chapter=3: type("B", (), {"secret": secret, "chapter": chapter})()  # noqa: E731
    assert auditor._established(beat("暗柜的密码是梅花"))  # said in chapter 2
    assert not auditor._established(beat("十年前林晚的母亲救过周伯的命"))  # first said in chapter 3
    assert not auditor._established(beat("暗柜的密码是梅花", chapter=2))  # no earlier chapter


def test_a_problem_flagged_with_another_diagnosis_is_reported_not_counted(mock):
    a = audit_story(chapters(), CAST, mock)
    truth = {
        "problems": [
            # The fixture calls the gift "contradicts"; this label only accepts "unmotivated".
            {
                "id": "P1",
                "kind": "character",
                "accept": ["unmotivated"],
                "character": "林晚",
                "chapter": 2,
                "evidence": [{"chapter": 2, "text": "把十文钱全给了他"}],
            },
        ],
        "traps": [],
    }
    s = score(a, truth, chapters())
    row = s["problem_rows"][0]
    assert not row["found"] and row["located_other_kind"]
    assert s["problems_found"] == 0 and s["located"] == 1
    assert row["located_other_kind"][0] not in s["unlabelled_issues"]


def test_a_note_read_off_the_act_is_not_what_it_goes_against(mock):
    def against_itself(system, prompt, schema):
        answer = motive_answer(prompt)
        if "乞丐" in prompt.split("\n", 1)[0]:
            # "Kind-hearted", read off the gift itself, as the thing the gift goes against.
            answer = {**answer, "reason_notes": [], "against_notes": [circular_note(prompt)]}
        return answer

    mock.on_schema("motive_check", against_itself)
    a = audit_story(chapters(), CAST, mock)
    gift = next(j for j in a.judgements if "乞丐" in a.beat(j.beat).action)
    assert gift.conflicts == []
    assert any("dropped conflict" in c and "circular" in c for c in gift.checks)
    assert gift.verdict == "unverified"  # a reason ("同情") was stated, none grounded


def test_a_setup_paid_off_in_other_words_is_not_dangling(mock):
    # 铜钥匙 never comes back as a word, but the model finds the beat that pays it off.
    mock.on_schema(
        "setup_payoff",
        lambda s, p, _: {"paid_off_by": re.findall(r"(B\d+)（", p)[0], "why": "换了说法"},
    )
    a = audit_story(chapters(), CAST, mock)
    assert not [i for i in a.issues if i.kind == "dangling_setup"]
    assert a.usage["calls_by_stage"]["payoff"] == 1


def _row(family, kind, chapter, refs, character="程歌", severity=2, title="t"):
    from novelforge.narrative.audit import Evidence

    return dict(
        family=family, kind=kind, chapter=chapter, chapters=[chapter], character=character,
        severity=severity, title=title, explanation="", rationale="r", fixes=[],
        evidence=[Evidence(chapter, 10 * len(refs), 10 * len(refs) + 5, title, "beat")],
        refs=list(refs),
    )  # fmt: skip


def test_one_scene_or_one_beat_is_one_finding():
    from novelforge.narrative.audit import _merge_rows

    rows = [
        _row("character", "contradicts", 3, ["B12", "N8", "N13"], title="打耳光", severity=3),
        _row("character", "contradicts", 3, ["B13", "N8"], title="当众斥责"),  # same scene
        _row("character", "contradicts", 3, ["B14", "N40"], title="唱歌"),  # another conflict
        _row("character", "contradicts", 5, ["B21", "N8"], title="潜入"),  # another chapter
        _row("plot", "causality", 4, ["B18", "B22"], character=None),
        _row("plot", "knowledge_leak", 5, ["B22"], severity=3),
    ]
    out = _merge_rows(rows, "zh")
    assert [(r["kind"], r["chapter"], r.get("merged", [])) for r in out] == [
        ("contradicts", 3, ["当众斥责"]),
        ("contradicts", 3, []),
        ("contradicts", 5, []),
        ("knowledge_leak", 5, ["causality"]),  # the code-checked diagnosis stays on top
    ]
    scene = out[0]
    assert scene["severity"] == 3 and scene["refs"] == ["B12", "N8", "N13", "B13"]
    assert len(scene["evidence"]) == 2 and "还有 1 处" in scene["rationale"]
    assert out[3]["refs"] == ["B22", "B18"] and "也被判为" in out[3]["rationale"]


def test_the_beat_that_reveals_an_earlier_reason_is_not_a_flaw(mock):
    from novelforge.narrative.audit import Beat, Judgement, Note, StoryAuditor

    auditor = StoryAuditor(chapters(), CAST, mock)
    a = auditor.audit
    reveal = Note("N9", "许校长", "background", "替程歌父亲还情", 3, "x", 100, 140)
    a.notes = [reveal]
    a.beats = [
        Beat("B2", 1, "许校长", True, "减学费", "q", 5, 20, False, "", "", "exact"),
        Beat("B8", 3, "许校长", True, "说出原因", "q", 90, 150, False, "", "", "exact"),
    ]
    j = lambda beat, verdict, by=None: Judgement(beat, verdict, verdict, 2, "", [], [], ["f"], by)  # noqa: E731
    a.judgements = [j("B2", "delayed", "N9"), j("B8", "contradicts")]
    auditor._reveals()
    assert a.judgements[1].verdict == "consistent" and a.judgements[1].fixes == []
    assert "explains B2" in a.judgements[1].checks[-1]
