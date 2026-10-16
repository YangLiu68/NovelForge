"""Chinese rule-based fact extractor (`rules-zh-v1`), the Chinese twin of `core/extraction.py`.

It reads the same predicates, so the contradiction detectors work unchanged: eye and hair
colour, age, handedness, birthplace, location, status (dead/alive), abilities (cannot /
learned / used) and hair dyeing (a change). Values are normalised to the English canonical
words (琥珀色 -> amber, 栗色 -> brown), Chinese numerals are parsed (五十六 -> 56).

Chinese has no word boundaries or capitals, so every rule is anchored on a character's name
or alias, and the words between the name and the fact (the gap) are checked:
- no other character's name, no pronoun (他/她/你/我), no dialogue quote;
- for attributes, no person noun such as 母亲 or 那人, which would own the eyes or hair
  instead, except in a 是… predicate (“苏婉是林家的丫头，一头乌黑的头发” is about 苏婉);
- a comma only where Chinese continues one subject across clauses (“林雪棠穿着灰色的呢大衣，
  眼睛却是琥珀色的”);
- for actions, no negation or intention (不/没/想/要/会/得), so “不会骑马” is not riding.

Modality, as in English:
- reported: inside “” 「」 『』
- recalled: a memory or an earlier time (记得、小时候、当年、十岁那年), or an age used as a time
  adverbial (“十二岁跟着叔叔来到雾港”); “像从前一样” is a comparison, not a memory
- hedged: perception, rumour or doubt in the clause (看上去、好像、听说、以为), or a condition
  before it in the sentence (如果、要是、梦见)
- asserted: everything else

A pronoun (她/他) counts only when one listed character with that sheet pronoun is named in
its sentence or the one before (`resolve_pronouns`); the claim records the resolution and is
0.1 less confident.

Not covered (v1): similes, euphemisms for death (走了), and places
without a place suffix (上海) unless they are on a character sheet.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from novelforge.core.domain import ChapterRef, CharacterRef, ExtractedClaim, Span
from novelforge.core.text import inside_dialogue, sentence_bounds

EXTRACTOR_ZH = "rules-zh-v1"
CLAIM_NAMESPACE = uuid.UUID("6c1f5c1e-2b7a-4c55-9a43-6f0d5e0b7a01")
CONFIDENCE = {"asserted": 0.9, "recalled": 0.8, "reported": 0.5, "hedged": 0.4}

# ---------------------------------------------------------------- numbers

_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
          "七": 7, "八": 8, "九": 9}  # fmt: skip
CN_NUM = r"(?:\d{1,3}|[零〇一二两三四五六七八九十廿卅百]{1,5})"


def parse_cn_number(raw: str) -> int | None:
    """十七 -> 17, 二十三 -> 23, 廿三 -> 23, 一百零二 -> 102, 17 -> 17; None if not a number."""
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    raw = raw.replace("廿", "二十").replace("卅", "三十")
    total, current = 0, None
    for ch in raw:
        if ch in "零〇" and total:
            continue  # 一百零二: a placeholder after a unit
        if ch in _DIGIT:
            if current is not None:
                return None  # 七八 is a range, not a number
            current = _DIGIT[ch]
        elif ch == "十":
            total += (1 if current is None else current) * 10
            current = None
        elif ch == "百":
            if current is None:
                return None
            total += current * 100
            current = None
        else:
            return None
    return total + (current or 0)


# ---------------------------------------------------------------- vocabulary

_CJK = r"一-鿿"
# Colour words, longest first, with their canonical value. Red is never an eye colour in
# Chinese prose (“红了眼睛” is crying), and 青 is too ambiguous for either.
_EYE_COLOURS = {
    "琥珀": "amber", "金黄": "amber", "金": "amber",
    "湛蓝": "blue", "碧蓝": "blue", "天蓝": "blue", "蔚蓝": "blue", "深蓝": "blue",
    "浅蓝": "blue", "冰蓝": "blue", "蓝": "blue",
    "碧绿": "green", "翠绿": "green", "翡翠": "green", "绿": "green", "碧": "green",
    "银灰": "grey", "铁灰": "grey", "灰": "grey",
    "乌黑": "black", "漆黑": "black", "墨黑": "black", "黑": "black",
    "浅褐": "brown", "深褐": "brown", "褐": "brown", "棕": "brown", "茶": "brown",
    "栗": "brown", "咖啡": "brown",
    "榛": "hazel", "紫罗兰": "violet", "紫": "violet",
}  # fmt: skip
_HAIR_COLOURS = {
    "乌黑": "black", "漆黑": "black", "墨黑": "black", "黑": "black", "乌": "black",
    "青丝": "black",
    "花白": "grey", "灰白": "grey", "银灰": "grey", "灰": "grey",
    "雪白": "white", "银白": "silver", "银": "silver", "白": "white",
    "金黄": "blond", "淡金": "blond", "金": "blond", "亚麻": "blond",
    "火红": "red", "赤红": "red", "红": "red", "赤": "red",
    "栗": "brown", "棕": "brown", "褐": "brown", "咖啡": "brown",
}  # fmt: skip


def _alt(words: Iterable[str]) -> str:
    return "|".join(sorted(words, key=len, reverse=True))


_EYE_C = rf"(?P<val>{_alt(_EYE_COLOURS)})"
_HAIR_C = rf"(?P<val>{_alt(w for w in _HAIR_COLOURS if w != '青丝')})"
_EYES = r"(?:眼睛|眼眸|眸子|双眸|眼珠子|眼珠|眼仁|瞳仁|瞳孔|眼瞳|瞳|眸)"
_HAIRS = r"(?:头发|长发|短发|卷发|鬈发|发丝|秀发|发辫|辫子|鬓发)"
# A bare 发 after a colour (黑发, 银发) but not 发亮, 发白, 发抖 ...
_BARE_HAIR = r"发(?![亮光白黑红青紫抖颤烫麻愣呆怔酸胀涩苦干硬软凉冷热毛疯狠怒火现觉出生])"
_COPULA = r"(?:是|呈|成了|泛着|透着|带着|还是|仍是|仍然是|依旧是|一直是|都是|已经是|也是|却是|则是)"
_PLACE_SUFFIX = r"(?:省|府|州|县|城|镇|乡|村|寨|庄|港|湾|岛|渡|堡|京|津|浦|埠|屯)"
# Common nouns that end like a place name but name no place.
_GENERIC_PLACES = frozenset({
    "村庄", "城镇", "乡村", "县城", "京城", "州府", "海港", "港湾", "渔村", "山村", "小镇",
    "古镇", "小城", "城池", "都城", "边城", "海岛", "小岛", "孤岛", "山庄", "庄园", "渡口",
    "码头", "府城", "省城", "进城", "出城", "满城", "全城", "回乡", "家乡", "故乡", "他乡",
    "异乡", "下乡", "老家", "钱庄", "票庄", "布庄", "茶庄", "饭庄", "酒庄", "农庄", "绸庄",
    "米庄", "粮庄", "银庄", "当庄",
})  # fmt: skip
# A place value never contains these (生在穷人家, 回到了家里).
_NOT_PLACE = re.compile(r"[家户人个一些年月日天时候夜晚早里屋房门院边上下中前后这那哪么]")
SKILLS_ZH = {"游泳": "swim", "凫水": "swim", "泅水": "swim", "水性": "swim", "骑马": "ride",
             "识字": "read", "认字": "read", "读书": "read", "写字": "write"}  # fmt: skip
_SKILL = rf"(?P<val>{_alt(SKILLS_ZH)})"
_NOT_BIRTHDAY = r"(?!的?生日|的?寿辰|大寿|[零〇一二两三四五六七八九十])"

_PRONOUN = re.compile(r"[他她它你我您]")
# Intention, ability or obligation before an action: not an event that happened.
_MODAL = re.compile(
    r"(?:要|想|会|能|敢|肯|得|该|打算|准备|学着?|学会了?|怕|快要|将要|将|正要)[^，]{0,2}$"
)
_NEGATED = re.compile(r"[不没未别莫](?:有|曾|再|敢|会|能|肯)?[^，]{0,1}$")
_PERSON = re.compile(
    r"母亲|父亲|娘亲|爹爹|妈妈|爸爸|哥哥|姐姐|弟弟|妹妹|兄长|嫂子|叔叔|伯伯|舅舅|舅母|姨妈|姑姑|"
    r"婶婶|奶奶|爷爷|外婆|外公|祖母|祖父|儿子|女儿|丈夫|妻子|夫人|孩子|丫头|丫鬟|女人|男人|姑娘|"
    r"小伙子|老人|老头|老太太|先生|太太|小姐|少爷|师父|师傅|师兄|师姐|师弟|师妹|朋友|伙计|掌柜|"
    r"客人|那人|这人|此人|有人|旁人|别人|众人|路人|陌生人|对方|侍女|侍卫|[娘爹妈]"
)
_OWNED_BY_OTHER = re.compile(r"的人|(?:的)?(?:" + _PERSON.pattern + r")")
# A person noun inside a 是… predicate describes the subject: 苏婉是林家的丫头.
_PREDICATE_NOUN = re.compile(r"是[^，。！？；]{0,10}")
_GAP_STOP = re.compile(r"[。！？；：“”「」『』\n]")
# Adverbs and perception words that may sit between 眼睛/头发 and the colour.
_ADV = (
    r"(?:看上去|看起来|似乎|好像|仿佛|显得|还|仍然|仍|依旧|都|也|却|则|倒|本来|原本|一直|向来|几乎|"
    r"有些|有点|微微|竟然|竟|居然|总是|天生|生来|原来|其实|分明|明明)"
)
# “头发还像从前一样，是栗色的”: the same as before, said of now.
_SAME = r"(?:(?:还|仍|依旧|也)?(?:像|和|跟|同)(?:从前|以前|过去|当年|小时候)一样，?)?"
_SHADE = r"(?:一种|淡淡的|浅浅的|深深的|很深的|很浅的|极淡的|纯粹的)?"


# ---------------------------------------------------------------- rules


@dataclass(frozen=True)
class _Rule:
    predicate: str
    tail: str  # regex matched right after the gap
    gap: int  # max characters between the name and the tail
    kind: str  # "attribute" | "action" | "state"
    commas: bool = False  # may the gap cross a comma (one subject across clauses)?


_RULES: list[_Rule] = [
    # 林雪棠的眼睛是灰色的 / 林雪棠的眼睛看上去几乎是黑的
    _Rule("eye_color", rf"的?{_EYES}{_SAME}{_ADV}{{0,3}}{_COPULA}?{_ADV}{{0,2}}{_SHADE}{_EYE_C}(?:色的|色)?", 4, "attribute"),
    # 陈砚有一双黑眼睛 / 林雪棠灰色的眼睛 / 林雪棠穿着灰色的呢大衣，眼睛却是琥珀色的
    _Rule("eye_color", rf"(?:一双|那双|两只|双)?{_EYE_C}(?:色|颜色)?的?{_EYES}", 8, "attribute", True),
    _Rule("eye_color", rf"(?<=，)(?:一双|那双)?{_EYES}{_ADV}{{0,3}}{_COPULA}{_ADV}{{0,2}}{_SHADE}{_EYE_C}(?:色的|色)?",
          30, "attribute", True),
    # 林雪棠的头发是黑色的
    _Rule("hair_color", rf"的?{_HAIRS}{_SAME}{_ADV}{{0,3}}{_COPULA}?{_ADV}{{0,2}}{_SHADE}{_HAIR_C}(?:色的|色)?", 4, "attribute"),
    # 林雪棠一头黑发 / 林雪棠栗色的头发 / 苏婉是林家的丫头，今年二十岁，一头乌黑的头发
    _Rule("hair_color", rf"(?:一头|满头|一把)?{_HAIR_C}(?:色|颜色)?的?(?:{_HAIRS}|{_BARE_HAIR})", 30,
          "attribute", True),
    _Rule("hair_color", r"(?:一头|满头)?(?P<val>青丝)", 30, "attribute", True),
    # 林雪棠把头发染成了栗色 / 林雪棠染了一头红发
    _Rule("hair_color.change", rf"(?:把|将)(?:头发|一头[^，。]{{0,4}}发)(?:染|漂)成了?[^，。]{{0,3}}?{_HAIR_C}(?:色的|色)?",
          6, "action"),
    _Rule("hair_color.change", rf"(?:染|漂)了一头{_HAIR_C}(?:色|颜色)?的?(?:{_HAIRS}|发)", 6, "action"),
    # 林雪棠今年十七岁 / 周铁山五十六岁了 / 苏婉十岁那年 / 苏婉是林家的丫头，今年二十岁
    _Rule("age", rf"(?:今年|已经|已|才|刚|刚刚|正|都|也|当时|时年|那年)?(?:满|过了|到了)?(?P<val>{CN_NUM})(?:周)?岁{_NOT_BIRTHDAY}",
          0, "attribute"),
    _Rule("age", rf"(?<=，)(?:今年|已经|才|刚|刚满|年方|年仅)?(?P<val>{CN_NUM})(?:周)?岁{_NOT_BIRTHDAY}", 20, "attribute",
          True),
    _Rule("age", rf"(?:年方|芳龄|年纪|年届|年仅|刚满)(?P<val>{CN_NUM})(?:周)?岁?", 2, "attribute"),
    # 陈砚是左撇子 / 陈砚惯用右手
    _Rule("handedness", r"(?:是个|是|天生是个|天生|一向是|从小就是)?(?P<val>左)撇子", 6, "attribute"),
    _Rule("handedness", r"(?:惯用|习惯用|惯使|一向用|只惯用)(?P<val>左|右)手", 6, "attribute"),
    # 陈砚生在临江县 / 陈砚是青州人
    _Rule("birthplace", r"(?:生在|出生在|出生于|生于|降生在|落地在)(?P<val>{PLACE})", 6, "state"),
    _Rule("birthplace", rf"是(?P<val>[{_CJK}]{{1,5}}?{_PLACE_SUFFIX})人", 4, "state"),
    # 顾明远回到了雾港 / 林雪棠在雾港
    _Rule("location", r"(?:到了|来到|回到了|回到|抵达|到达|赶到|进了|返回|回了|去了)(?P<val>{PLACE})",
          12, "action", True),
    _Rule("location", r"(?<!生)(?:人在|正在|还在|仍在|已在|住在|待在|呆在|留在|在)(?P<val>{PLACE})(?!外|以外|之外|附近|一带|周围)",
          4, "action"),
    # 顾明远死了 / 顾明远已经去世了
    _Rule("status", r"(?P<val>死了)(?![" + _CJK + r"])", 4, "action"),
    _Rule("status", r"(?P<val>去世|过世|病逝|病故|逝世|身亡|丧命|毙命|咽了气|断了气|遇害|被杀|被人杀了|"
          r"淹死|吊死|饿死|冻死|战死|病死|死在|死于)", 4, "action"),
    _Rule("status", r"(?P<val>还活着|活着|没死|没有死|活了下来|活下来了|尚在人世|还在人世)", 4, "state"),
    # 苏婉不会游泳 / 陈砚学会了骑马 / 陈砚骑着马 / 苏婉……游到孩子身边
    _Rule("ability.cannot", rf"(?:不会|不懂|不识|从没学过|从来没学过|没学过|学不会|一直不会|根本不会|并不会){_SKILL}",
          4, "state"),
    _Rule("ability.cannot", r"(?:是个|是)?旱鸭子(?P<val>)", 4, "state"),
    _Rule("ability.cannot", r"(?P<val>大字不识|一字不识|目不识丁|不识得字)", 4, "state"),
    _Rule("ability.learned", rf"(?:学会了|学会|终于会了|学了){_SKILL}", 10, "state"),
    _Rule("ability.used", r"(?P<val>游到|游向|游回|游过|游了过去|游了回来|游上|游出|游进|游近|泅过|泅到|凫到|凫过)",
          14, "action", True),
    _Rule("ability.used", r"(?P<val>骑着马|骑马|骑上马|骑了马|策马|纵马|打马|跨上马|翻身上马|骑着一匹|骑了一匹)",
          8, "action", True),
    _Rule("ability.used", r"(?P<val>念了|念着|念完|读了|读着|读完|默读|朗读)(?:一遍|两遍|几遍)?[这那]?[封张份本行]?"
          r"(?=信|告示|账本|字条|纸条|书|报|文书|契约|帖子|诗)", 6, "action"),
]  # fmt: skip
_USED_VERB = {"游": "swim", "泅": "swim", "凫": "swim", "骑": "ride", "策": "ride", "纵": "ride",
              "打": "ride", "跨": "ride", "翻": "ride", "念": "read", "读": "read", "默": "read",
              "朗": "read"}  # fmt: skip

# 十七岁的林雪棠 / 生在青石镇的程歌
_BEFORE_RULES: list[tuple[str, str]] = [
    ("age", rf"(?<![零〇一二两三四五六七八九十廿卅百\d])(?P<val>{CN_NUM})(?:周)?岁的(?={{who}})"),
    ("birthplace", r"(?:生在|出生在|出生于|生于)(?P<val>{PLACE})的(?={who})"),
]

_RECALL = re.compile(
    r"记得|认得|想起|想当年|回想|当年|从前|小时候|幼时|儿时|年轻时|年轻的时候|早年|曾经|以前|那时|那会儿|"
    r"前世|上辈子|上一世"
)
_COMPARE = re.compile(r"[像和跟同如比]$")  # “像从前一样”: a comparison, not a memory
_AFTER_PAST = re.compile(r"那年|那会|的时候|时候|时(?![间刻])|之前|以前|起|以后|开始")
_PAST_TIME = re.compile(r"那年|那天|那晚|那夜|那时|当年|的时候")
_HEDGE = re.compile(
    r"好像|似乎|仿佛|像是|也许|或许|大概|大约|恐怕|怕是|兴许|据说|听说|传说|传言|有人说|都说|人说|"
    r"谣传|以为|看上去|看起来|显得|隐约|依稀|几乎"
)
_CONDITION = re.compile(
    r"如果|要是|假如|倘若|若是|万一|假使|假设|即使|哪怕|但愿|希望|巴不得|想象|设想|梦见|梦里|梦中"
)
_OFFSET = re.compile(
    rf"(?P<n>{CN_NUM}|几)(?P<unit>天|日|个?星期|个?礼拜|周)(?:之|以)?后|过了(?P<n2>{CN_NUM})天|"
    r"(?P<next>第二天|次日|翌日|隔天|隔日|第二日|转天)"
)


@dataclass(frozen=True)
class _Mention:
    start: int
    end: int
    character: CharacterRef
    resolved: dict | None = None  # set for a pronoun: which name it was resolved to


RESOLVED_PENALTY = 0.1  # a fact reached through a pronoun is less certain
_GENDER = {"she": "她", "he": "他"}


def _pronoun_of(c: CharacterRef) -> str | None:
    raw = str(c.attributes.get("pronouns") or "").strip().lower()
    return _GENDER.get(re.split(r"[/,\s]+", raw)[0]) if raw else None


def resolve_pronouns(body: str, mentions: list[_Mention]) -> list[_Mention]:
    """她/他 in narration, resolved only when unambiguous: the nearest sentence (the pronoun's
    own, before it; else the previous one in the same paragraph) that names a listed character
    names exactly one, in narration, and its sheet pronoun matches. 他们/其他/他人 are not
    pronouns for one person."""
    out = []
    for m in re.finditer(r"(?<!其)[他她](?![们人乡])", body):
        p = m.start()
        if inside_dialogue(body, p):
            continue
        para = body.rfind("\n\n", 0, p)
        para = 0 if para < 0 else para + 2
        s, _ = sentence_bounds(body, p, p + 1)
        named = [x for x in mentions if s <= x.start < p]
        if not named and s - 2 >= para:
            prev = max(sentence_bounds(body, s - 2, s - 1)[0], para)
            named = [x for x in mentions if prev <= x.start < s]
        if len({x.character.id for x in named}) != 1:
            continue
        narrated = [x for x in named if not inside_dialogue(body, x.start)]
        if not narrated or _pronoun_of(narrated[-1].character) != m.group(0):
            continue
        ante = narrated[-1]
        out.append(
            _Mention(p, p + 1, ante.character,
                     {"via": "pronoun", "pronoun": m.group(0), "pronoun_start": p,
                      "antecedent_start": ante.start})
        )  # fmt: skip
    return out


def surface_forms_zh(characters: Iterable[CharacterRef]) -> dict[str, CharacterRef]:
    """Names and declared aliases; a form claimed by two characters is dropped."""
    owners: dict[str, list[CharacterRef]] = {}
    for c in characters:
        for f in {c.name.strip(), *(a.strip() for a in c.aliases)}:
            if len(f) >= 2:
                owners.setdefault(f, []).append(c)
    return {f: cs[0] for f, cs in owners.items() if len({c.id for c in cs}) == 1}


def _place_pattern(characters: list[CharacterRef]) -> str:
    """A place: a run ending in a place suffix, or a place named on a character sheet."""
    known = {str(c.attributes.get("birthplace", "")).strip() for c in characters}
    known = {k for k in known if k}
    suffixed = rf"[{_CJK}]{{1,5}}?{_PLACE_SUFFIX}"
    return rf"(?:{_alt(known)}|{suffixed})" if known else suffixed


def _gap_ok(body: str, start: int, end: int, rule: _Rule, mentions: list[_Mention]) -> bool:
    gap = body[start:end]
    if _GAP_STOP.search(gap) or (not rule.commas and "，" in gap):
        return False
    if any(start <= m.start < end for m in mentions):
        return False
    if _PRONOUN.search(gap):
        return False
    if rule.kind == "attribute" and _PERSON.search(_PREDICATE_NOUN.sub("", gap)):
        return False
    if (
        rule.kind == "action"
        and rule.predicate != "hair_color.change"
        and (_NEGATED.search(gap) or _MODAL.search(gap))
    ):
        return False
    # 差点冻死 is not a death; 几乎不会游泳 is not “cannot”.
    near = re.search(r"差点|险些|几乎|差一点|快要", gap)
    return not (near and rule.predicate in ("status", "ability.cannot"))


def _clause(body: str, start: int, end: int) -> tuple[int, int]:
    """The comma clause(s) spanning body[start:end]."""
    s, e = sentence_bounds(body, start, end)
    left = max(body.rfind("，", s, start), body.rfind("、", s, start))
    right = [i for i in (body.find("，", end, e), body.find("、", end, e)) if i >= 0]
    return (left + 1 if left >= 0 else s), (min(right) if right else e)


def _modality(body: str, start: int, end: int, predicate: str, val_end: int) -> str:
    if inside_dialogue(body, start):
        return "reported"
    cs, ce = _clause(body, start, end)
    clause = body[cs:ce]
    for m in _RECALL.finditer(clause):
        if not _COMPARE.search(clause[: m.start()]):
            return "recalled"
    if predicate in ("age", "location", "status"):
        after = body[val_end : val_end + 4]
        if predicate == "age":
            after = after.lstrip("岁周")
        if _AFTER_PAST.match(after):
            return "recalled"
        # “她死在十九岁那年的腊月”: a past time later in the clause.
        if predicate != "age" and _PAST_TIME.search(body, val_end, ce):
            return "recalled"
    if predicate == "age":
        # An age followed by an action is a time adverbial: “十二岁跟着叔叔来到雾港”.
        after = re.sub(r"^周?岁", "", body[val_end : val_end + 3])
        if after and not re.match(r"[，。！？；、了的”」\s]", after):
            return "recalled"
    if predicate == "location" and re.search(rf"{CN_NUM}岁", clause):
        return "recalled"
    s, _ = sentence_bounds(body, start, end)
    if _HEDGE.search(clause) or _CONDITION.search(body, s, end):
        return "hedged"
    return "asserted"


def _normalize(predicate: str, raw: str, tail: str) -> tuple[str, str] | None:
    raw = raw.strip()
    if predicate == "eye_color":
        return predicate, _EYE_COLOURS[raw]
    if predicate in ("hair_color", "hair_color.change"):
        return "hair_color", _HAIR_COLOURS[raw]
    if predicate == "age":
        n = parse_cn_number(raw)
        return None if n is None or n > 130 else ("age", str(n))
    if predicate == "handedness":
        return predicate, "left" if raw == "左" else "right"
    if predicate in ("birthplace", "location"):
        bad = _NOT_PLACE.search(raw) or raw in _GENERIC_PLACES
        return None if bad else (predicate, raw)
    if predicate == "status":
        alive = raw in (
            "还活着",
            "活着",
            "没死",
            "没有死",
            "活了下来",
            "活下来了",
            "尚在人世",
            "还在人世",
        )
        return "status", "alive" if alive else "dead"
    mode = predicate.split(".", 1)[1]
    if predicate == "ability.used":
        skill = _USED_VERB.get(raw[:1])
    elif "旱鸭子" in tail:
        skill = "swim"
    elif raw in ("大字不识", "一字不识", "目不识丁", "不识得字"):
        skill = "read"
    else:
        skill = SKILLS_ZH.get(raw)
    return None if skill is None else (f"ability:{skill}", mode)


def day_offset_zh(body: str, start: int) -> int:
    s, _ = sentence_bounds(body, start, start + 1)
    found = list(_OFFSET.finditer(body, s, start))
    if not found:
        return 0
    m = found[-1]
    if m.group("next"):
        return 1
    raw = m.group("n") or m.group("n2")
    n = 3 if raw == "几" else parse_cn_number(raw) or 0
    unit = m.group("unit") or "天"
    return n * (7 if unit[-1] in "期拜周" else 1)


def extract_claims_zh(
    chapter: ChapterRef, characters: Iterable[CharacterRef]
) -> list[ExtractedClaim]:
    characters = list(characters)
    forms = surface_forms_zh(characters)
    body = chapter.body
    if not forms or not body:
        return []
    who = re.compile(_alt(re.escape(f) for f in forms))
    mentions = [_Mention(m.start(), m.end(), forms[m.group(0)]) for m in who.finditer(body)]
    anchors = mentions + resolve_pronouns(body, mentions)
    place = _place_pattern(characters)

    found: list[tuple] = []
    for rule in _RULES:
        tail = re.compile(
            rf"(?P<gap>[^。！？；\n]{{0,{rule.gap}}}?)(?:{rule.tail.replace('{PLACE}', place)})"
        )
        for m in anchors:
            t = tail.match(body, m.end)
            if t is None or not _gap_ok(
                body, m.end, t.start() + len(t.group("gap")), rule, mentions
            ):
                continue
            inner = body[m.end : t.start("val")]
            if _PRONOUN.search(inner) or any(m.end <= x.start < t.start("val") for x in mentions):
                continue
            if rule.kind == "attribute" and _OWNED_BY_OTHER.match(body, t.end()):
                continue  # 一头白发的老人: the hair belongs to the person after it
            if (
                rule.predicate == "status"
                and _OWNED_BY_OTHER.match(body, t.end())
                and body[t.end()] == "的"
            ):
                continue  # 她过世的母亲: the mother died, not her
            start = m.start
            if m.resolved is not None:
                # The quote starts at the name when it is in this sentence, else at the pronoun.
                s, _ = sentence_bounds(body, m.start, m.end)
                ante = m.resolved["antecedent_start"]
                start = ante if ante >= s else m.start
            found.append(
                (rule.predicate, t.group("val"), m.character, body[m.start : m.end], start,
                 t.end(), t.end("val"), t.group(0), m.resolved, m.start)
            )  # fmt: skip
    who_src = _alt(re.escape(f) for f in forms)
    for predicate, template in _BEFORE_RULES:
        pattern = re.compile(template.replace("{PLACE}", place).replace("{who}", who_src))
        for t in pattern.finditer(body):
            m = next((x for x in mentions if x.start == t.end()), None)
            if m is None:
                continue
            found.append(
                (predicate, t.group("val"), m.character, body[m.start : m.end], t.start(), m.end,
                 t.end("val"), t.group(0), None, t.start())
            )  # fmt: skip

    seen: set[tuple[str, int]] = set()
    claims: list[ExtractedClaim] = []
    for (
        predicate,
        raw,
        character,
        subject_text,
        start,
        end,
        val_end,
        tail,
        resolved,
        anchor,
    ) in found:
        normalized = _normalize(predicate, raw, tail)
        if normalized is None:
            continue
        final, value = normalized
        if (final, end) in seen:
            continue  # the same words already gave this fact
        seen.add((final, end))
        modality = _modality(body, anchor, end, final, val_end)
        offset = day_offset_zh(body, start)
        details: dict = {"change": True} if predicate.endswith(".change") else {}
        if offset:
            details["day_offset"] = offset
        confidence = CONFIDENCE[modality]
        if resolved is not None:
            details["resolved"] = resolved
            confidence = round(confidence - RESOLVED_PENALTY, 2)
        key = f"{chapter.id}|{chapter.version}|{EXTRACTOR_ZH}|{final}|{start}|{end}"
        claims.append(
            ExtractedClaim(
                id=str(uuid.uuid5(CLAIM_NAMESPACE, key)),
                chapter_id=chapter.id,
                chapter_version=chapter.version,
                subject_id=character.id,
                subject_text=subject_text,
                predicate=final,
                value=value,
                raw_value=raw,
                modality=modality,
                confidence=confidence,
                effective_day=None if chapter.story_day is None else chapter.story_day + offset,
                time_certainty="unknown" if chapter.story_day is None else "chapter_day",
                extractor=EXTRACTOR_ZH,
                spans=(Span(chapter.id, chapter.version, start, end, body[start:end]),),
                details=details,
            )
        )
    claims.sort(key=lambda c: (c.spans[0].start, c.predicate))
    return claims
