"""Extraction prompt. PROMPT_VERSION is part of every extraction job's idempotency key."""

from __future__ import annotations

import hashlib

from novelforge.core.domain import ChapterRef, CharacterRef

SYSTEM = """You extract facts from one chapter of a novel for a continuity database.

Rules:
- Extract only what THIS chapter's text states. Do not use outside knowledge or guess.
- Every fact needs a quote: copy 3 to 40 words EXACTLY from the chapter text, character for
  character, that states the fact. Facts without an exact quote are discarded.
- subject: the character's name exactly as listed in CHARACTERS (use the full name). Use "world"
  for world rules, and for events, foreshadowing or causal links with no single character.
- modality: "asserted" when the narrator states it as fact; "hedged" for perception, rumour or
  uncertainty ("seemed", "almost", "some said"); "reported" when it is inside a character's
  dialogue; "recalled" for memories or past habits ("remembered how ... used to").
- confidence: your confidence (0 to 1) that the fact is stated as described.
- day_offset: days after the chapter's starting day when the fact holds, if the text says so
  ("three days later" -> 3, "the next morning" -> 1); otherwise 0.
- Resolve pronouns to the right character when the text makes it unambiguous.

Kinds (value / object):
- eye_color, hair_color: the colour word. handedness: left or right. birthplace: place name.
- age: the age in years as digits.
- location: place name where the character is at this point in the story.
- death: the character dies or is stated dead (value: cause or place, may be empty).
- alive: the character is explicitly stated to be alive.
- ability_cannot / ability_learned / ability_used: object = the skill as one verb (swim, read,
  ride, sail, write, ...); value = a short description.
- relationship: value = relation (sibling, parent, rival, employer, friend, ...); object = the
  other character's full name.
- event: value = one-sentence description of a plot event.
- world_rule: value = the rule of the story world in one sentence (magic, physics, law, custom).
- foreshadowing: value = the unresolved set-up (a mystery, an object, a promise) in one sentence.
- causal: value = "<cause> => <effect>".
Use "" for object when it does not apply. Return {"facts": []} if nothing qualifies."""

PROMPT_VERSION = "extract-v1-" + hashlib.sha1(SYSTEM.encode()).hexdigest()[:8]

# The same task for Chinese chapters. Colour words stay as written (normalised in code, so the
# quote can be checked to contain them); quotes are measured in characters, not words; modality
# cues and the traps of Chinese prose (a modifier owned by someone else, ranges like 七八岁, an age
# told as a memory) are spelled out.
SYSTEM_ZH = """你为一部中文小说的连续性数据库，从其中一章里提取事实。

规则：
- 只提取本章正文明确写出的事实，不用外部知识，不猜测，不做推断。
- 每条事实都要有 quote：从正文中逐字复制 4 到 60 个字，必须和原文一字不差（包括标点），而且这段
  原文本身就写出了这条事实。没有原文的事实会被丢弃。
- subject：人物名，用「人物」列表中的全名。世界规则、事件、伏笔、因果没有单一人物时写 "world"。
- 他、她等代词只有在上下文能唯一确定是谁时才算作那个人物；不能确定就不要提取。修饰别人的词不要算到
  这个人物头上（“她过世的母亲”说的是母亲，不是她）。
- modality（语气）：
  - "asserted"：叙述者直接陈述的事实。
  - "reported"：写在人物对话里（“”「」『』之内）的内容，不管说话人说得多肯定。
  - "recalled"：回忆、往事、前世、从前的样子或习惯（当年、那年、记得、小时候、前世、上辈子），
    包括把头发染成新颜色之前的旧发色。
  - "hedged"：传闻、猜测、看起来如此（听说、据说、似乎、好像、仿佛、像是、看着像），以及带条件或假设
    的说法。
- confidence：你确信这条事实就是这样写出的程度（0 到 1）。
- day_offset：正文写明事情发生在本章开始之后几天（三天后 → 3，次日、第二天 → 1）时填天数，否则 0。

种类（value / object）：
- eye_color：眼睛的颜色。value 照抄原文的颜色词（琥珀、灰、黑、碧绿……）。比喻不算。
- hair_color：头发的颜色，value 照抄原文的颜色词（乌黑、花白、银白、栗红……）。染发时新颜色照常
  提取，旧颜色是 recalled。正文自己写出或解释了头发颜色为什么变了（染、漂、剪掉染过的头发后长回
  原色、原来的颜色其实是染出来的）时，变化后的那条 object 写 "change"；没有任何解释的前后不一致
  不是变化，object 照常写 ""。
- handedness：惯用手，value 为 left 或 right（左撇子、惯用左手、使右手刀……）。
- birthplace：出生地，value 照抄原文地名（生在X、X人氏、出生于X）。
- age：年龄，value 为阿拉伯数字（今年五十三了 → 53）。七八岁这类约数不提取；在回忆里说的年龄
  （那年她才九岁）是 recalled。
- location：人物在故事此刻所在的地方，value 照抄原文地名。
- presence：人物此刻在场并且在做事（坐着、走进来、开口说话……），value 写 "present"。
- death：人物死了，或被说成已经死了（value：死因或地点，可为空）。
- alive：明确写人物还活着。
- ability_cannot / ability_learned / ability_used：object 是一个英文技能词：
  swim（游泳、凫水、会水）、ride（骑马）、read（识字、读信）、write（写字）、sail（驾船）等；
  value 是简短的中文描述。
  不会某项技能是 ability_cannot；学会、被人教会是 ability_learned；在本章里实际做了是 ability_used。
- relationship：value 为关系（sibling、parent、rival、employer、friend……），object 为另一个人物的
  全名。
- event：value 用一句话描述情节事件。
- world_rule：value 用一句话描述故事世界的规则（法术、律法、风俗……）。
- foreshadowing：value 用一句话描述尚未揭开的伏笔。
- causal：value 为 "<原因> => <结果>"。
object 不适用时写 ""。没有可提取的事实时返回 {"facts": []}。"""

PROMPT_VERSION_ZH = "extract-zh-v2-" + hashlib.sha1(SYSTEM_ZH.encode()).hexdigest()[:8]


def system_for(body: str) -> tuple[str, str]:
    """(system prompt, prompt version) for a chapter's language."""
    from novelforge.core.lang import is_chinese

    return (SYSTEM_ZH, PROMPT_VERSION_ZH) if is_chinese(body) else (SYSTEM, PROMPT_VERSION)


def user_prompt(
    chapter: ChapterRef, characters: list[CharacterRef], text: str, part: tuple[int, int] = (1, 1)
) -> str:
    from novelforge.core.lang import is_chinese

    if is_chinese(chapter.body):
        cast = "\n".join(
            f"- {c.name}" + (f"（又称：{'、'.join(c.aliases)}）" if c.aliases else "")
            for c in sorted(characters, key=lambda c: c.name)
        )
        when = "未知" if chapter.story_day is None else f"故事第 {chapter.story_day} 天"
        part_note = f"（第 {part[0]} 部分，共 {part[1]} 部分）" if part[1] > 1 else ""
        return (
            f"人物：\n{cast or '- （未列出）'}\n\n"
            f"第 {chapter.number} 章：{chapter.title}{part_note}\n时间：{when}\n\n"
            f"正文：\n<<<\n{text}\n>>>"
        )
    cast = "\n".join(
        f"- {c.name}" + (f" (also: {', '.join(c.aliases)})" if c.aliases else "")
        for c in sorted(characters, key=lambda c: c.name)
    )
    when = "unknown" if chapter.story_day is None else f"story day {chapter.story_day}"
    part_note = f" (part {part[0]} of {part[1]})" if part[1] > 1 else ""
    return (
        f"CHARACTERS:\n{cast or '- (none listed)'}\n\n"
        f"CHAPTER {chapter.number}: {chapter.title}{part_note}\nTIME: {when}\n\n"
        f"TEXT:\n<<<\n{text}\n>>>"
    )
