"""Chinese wording for contradiction findings.

The detectors (`core/contradictions.py`) write English; for a Chinese novel each finding's
explanation and suggestion are rewritten from its `params` (the same values and numbers), so a
Chinese author reads 「陈砚的惯用手前后不一致」, not English around Chinese quotes. Kinds, IDs,
evidence and fingerprints are unchanged.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from novelforge.core.contradictions import Finding

LABELS = {
    "eye_color": "眼睛颜色",
    "hair_color": "发色",
    "handedness": "惯用手",
    "birthplace": "出生地",
    "age": "年龄",
}
COLOURS = {
    "black": "黑色", "grey": "灰色", "blue": "蓝色", "green": "绿色", "brown": "棕色",
    "amber": "琥珀色", "hazel": "浅褐色", "violet": "紫色", "blond": "金色", "red": "红色",
    "auburn": "赤褐色", "white": "白色", "silver": "银色",
}  # fmt: skip
SKILLS = {"swim": "游泳", "ride": "骑马", "read": "识字", "write": "写字", "sail": "驾船"}


def show(predicate: str, value: str) -> str:
    if predicate in ("eye_color", "hair_color"):
        return COLOURS.get(value.lower(), value)
    if predicate == "handedness":
        return {"left": "左手", "right": "右手"}.get(value.lower(), value)
    if predicate == "age":
        return f"{value} 岁"
    return value


def chapters(numbers: list[int]) -> str:
    return "第 " + "、".join(str(n) for n in sorted(set(numbers))) + " 章"


def to_chinese(f: Finding) -> Finding:
    """The finding with Chinese explanation and suggestion; unchanged if the kind is unknown."""
    p, name, pred = f.params, f.subject_name, f.predicate
    label = LABELS.get(pred, pred)
    if f.kind == "canon_conflict" and p:
        canon, value = show(pred, p["canon"]), show(pred, p["value"])
        where = chapters(p["chapters"])
        text = f"人物卡上{name}的{label}是“{canon}”，但{where}写的是“{value}”。"
        fix = f"把{where}改成“{canon}”；如果现在想用“{value}”，就改人物卡。"
    elif f.kind == "attribute_conflict" and p:
        sides = "；".join(f"{chapters(chs)}是“{show(pred, v)}”" for v, chs in p["sides"])
        text = f"{name}的{label}前后不一致：{sides}。"
        fix = (
            f"把{chapters(p['others'])}改成“{show(pred, p['keep'])}”（出现最多或最早的写法），"
            f"或在人物卡上写明{label}。"
        )
        if pred == "hair_color":
            fix += "如果是有意的改变（比如染发），在正文里写出改变的那一刻。"
    elif f.kind == "age_timeline" and p:
        allowed = " 或 ".join(str(n) for n in p["allowed"])
        text = (
            f"{name}在故事第 {p['a_day']} 天（第 {p['ch_a']} 章）{p['a']} 岁，"
            f"第 {p['b_day']} 天（第 {p['ch_b']} 章）{p['b']} 岁；中间过了 {p['elapsed']} 天，"
            f"年龄应该是 {allowed} 岁。"
        )
        fix = (
            f"把第 {p['ch_b']} 章的年龄改成 {allowed} 岁，或者把第 {p['ch_b']} 章挪到第 "
            f"{p['ch_a']} 章之后大约 {p['years']} 年。"
            if p["forward"]
            else f"把第 {p['ch_b']} 章的年龄改成 {allowed} 岁；故事时间往前走，年龄不能变小。"
        )
    elif f.kind == "dead_character_active" and p:
        text = (
            f"{name}在故事第 {p['death_day']} 天（第 {p['ch_death']} 章）已经死了，"
            f"第 {p['day']} 天（第 {p['ch']} 章）却又出现：“{p['quote']}”。"
        )
        fix = (
            f"把第 {p['ch']} 章这一段改成回忆或倒叙（放到第 {p['death_day']} 天之前），"
            f"换成别的角色，或者把死亡往后挪。"
        )
    elif f.kind == "location_conflict" and p:
        when = "同一天" if p["elapsed"] == 0 else f"{p['elapsed']} 天后"
        text = (
            f"{name}第 {p['a_day']} 天（第 {p['ch_a']} 章）在{p['a']}，{when}（第 {p['ch_b']} 章）"
            f"就到了{p['b']}，可路上要走 {p['need']} 天。"
        )
        fix = (
            f"把第 {p['ch_b']} 章的场景至少再往后挪 {p['need'] - p['elapsed']} 天，换一个地点，"
            f"或者在地点设定里改正路程天数。"
        )
    elif f.kind == "ability_conflict" and p:
        skill = SKILLS.get(p["skill"], p["skill"])
        c, u = p["ch_cannot"], p["ch_used"]
        text = (
            f"{name}不会{skill}（第 {c} 章，第 {p['day_cannot']} 天），之后也没写学会，"
            f"第 {u} 章（第 {p['day_used']} 天）却{skill}了。"
        )
        fix = f"在第 {c} 章和第 {u} 章之间写{name}学会{skill}，或者改掉第 {u} 章的动作。"
    else:
        return f
    return replace(f, explanation=text, suggestion=fix)
