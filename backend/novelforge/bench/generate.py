"""Synthetic novel generator for the NovelForge consistency benchmark.

Given a seed and a chapter count it simulates a small world (characters, places with travel
times, deaths, skills learned, world rules, foreshadowing, causal links), renders it to prose
from varied templates, injects labelled contradictions and labelled look-alike negatives, and
writes the ground truth next to the text. Everything is a pure function of (seed, chapters):
the same arguments produce byte-identical files.

Output folder layout (same as samples/, so `novelforge import-corpus` loads it):
    novel.yaml          characters (with partial character-sheet canon), chapter list
    chNNNN.md           chapters with front matter (number, title, story_day, story_time_label)
    ground_truth.yaml   contradictions, negatives, facts, retrieval queries,
                        foreshadowing, causal links

Templates are deliberately varied: some state a fact next to the character's name, some only
through a pronoun or an indirect phrasing. Each mention records its template id so failure
analysis can be broken down by phrasing.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DAYS_PER_YEAR = 365.25

EYE = ["grey", "green", "blue", "brown", "hazel", "amber"]
HAIR = ["black", "brown", "red", "blond", "grey", "auburn"]
HANDS = ["left", "right"]
SKILLS = {
    # skill: (cannot sentence, learn sentence, exercise sentence) templates
    "swim": (
        [
            "{N} could not swim.",
            "{N} had never learned to swim, and kept well back from the water.",
        ],
        [
            "{N} learned to swim that season, badly at first.",
            "That summer {N} finally learned to swim.",
        ],
        [
            "{N} swam out to the moored skiff and back.",
            "{N} dove from the pier and swam to the boat.",
        ],
    ),
    "read": (
        ["{N} could not read.", "{N} had never learned to read, and hid it well."],
        [
            "{N} learned to read from the harbour clerk's old primers.",
            "Over the winter {N} finally learned to read.",
        ],
        ["{N} read the letter aloud, slowly.", "{N} read the posted notice twice."],
    ),
    "ride": (
        ["{N} could not ride.", "{N} had never learned to ride and distrusted horses."],
        [
            "{N} learned to ride on the farm road outside town.",
            "That spring {N} finally learned to ride.",
        ],
        ["{N} rode out along the coast road at a gallop.", "{N} rode the grey mare to the ford."],
    ),
}
RULES = [
    {
        "id": "R1",
        "statement": "saltglass cannot be cut by any blade",
        "violation": "{N} cut a pane of saltglass cleanly in two with a kitchen knife.",
        "attempt": "{N} tried to cut the saltglass, but the knife skidded off it.",
    },
    {
        "id": "R2",
        "statement": "no lamp will burn below the sea wall",
        "violation": "{N} lit a lamp below the sea wall, and it burned steadily all night.",
        "attempt": "{N} tried to light a lamp below the sea wall; it guttered out at once.",
    },
    {
        "id": "R3",
        "statement": "no bird ever crosses the Grey Reach",
        "violation": "A gull flew straight across the Grey Reach while {N} watched.",
        "attempt": "The gulls turned back at the edge of the Grey Reach, as {N} knew they would.",
    },
    {
        "id": "R4",
        "statement": "a promise sworn on salt cannot be broken",
        "violation": "{N} broke the promise sworn on salt without a second thought.",
        "attempt": (
            "{N} wanted to break the promise sworn on salt, and found that it could not be done."
        ),
    },
]
FORESHADOW = [
    ("a locked iron box under the stairs", "opened the iron box"),
    ("a letter sealed with green wax", "broke the green wax seal"),
    ("a key that fitted no lock in the house", "found the lock that the key fitted"),
    ("a stranger watching the harbour from the cliff", "learned who the stranger on the cliff was"),
    ("a map with one island scratched out", "found the island scratched off the map"),
    ("a bell that rang with no one near it", "discovered why the bell rang by itself"),
    ("a name carved inside the lighthouse door", "found out whose name was carved in the door"),
    ("a ship that never answered signals", "boarded the silent ship"),
]
CAUSES = [
    ("the bridge at {P} had fallen", "{N} took the long road around the marsh"),
    ("the harbour master had been arrested", "{N} carried the dispatches alone"),
    ("the fever had reached {P}", "{N} turned back before the town gate"),
    ("the winter grain had spoiled", "{N} sold the boat to buy flour"),
    ("the lighthouse lamp had failed", "{N} spent the night ringing the fog bell"),
]
DEATH_CAUSES = [
    "of fever",
    "in the flood",
    "of a fall from the cliff path",
    "in the harbour fire",
    "of an old wound",
    "at sea",
]

# Filler vocabulary. Filler mentions characters and body words ("eyes", "hair", "hand") so that
# lexical retrieval has realistic distractors.
WEATHER = [
    "Rain came in off the sea and rattled the shutters.",
    "The fog sat on the harbour like wet wool.",
    "A hard wind scoured the quay and flung salt at the windows.",
    "The morning was bright and cold, the water flat as slate.",
    "Snow fell on the roofs and melted on the cobbles.",
    "The tide ran out and left the boats leaning in the mud.",
    "Thunder rolled somewhere beyond the Grey Reach.",
    "Gulls argued over the fish market all afternoon.",
]
OBJECTS = [
    "the ledger",
    "a cracked lantern",
    "the harbour charts",
    "a coil of tarred rope",
    "a basket of oysters",
    "the dispatch satchel",
    "a chipped teacup",
    "the brass compass",
    "a bundle of letters",
    "the tide table",
]
ACTIONS = [
    "counted the coins twice",
    "mended a torn sail",
    "argued with the ferryman",
    "sorted the morning post",
    "scraped ice from the step",
    "sharpened a pencil",
    "studied the tide table",
    "folded the charts away",
    "bought bread at the stall",
    "rubbed {p} tired eyes",
    "pushed the wind-blown hair from {p} face",
    "warmed {p} hands at the brazier",
    "climbed the lighthouse stair",
    "listened to the bell buoy",
    "wrote a short note",
    "stacked crates on the quay",
]
SPEECH = [
    '"We should have left yesterday," said {N}.',
    '"The tide will not wait for us," {N} said.',
    '"I have heard worse news," said {N}, "but not this week."',
    '"Bring the lantern," {N} said, "and the charts."',
    '"Nobody in this town listens," said {N}.',
]

# Scene description, used to build filler paragraphs between the plot sentences.
SCENE = [
    "The harbour bell clanged twice and fell silent.",
    "Somewhere below, a cart rattled over the cobbles.",
    "The smell of tar and wet rope hung over everything.",
    "A boy ran past with a basket of herring on his head.",
    "The lamplighter was already working his way along the sea road.",
    "Lantern light pooled on the floorboards.",
    "The kettle on the stove began to tick as it heated.",
    "Outside, the tide was turning, and the moored boats swung on their ropes.",
    "Someone had chalked a tally of ships on the harbour wall.",
    "The stairs creaked under every step.",
    "A cold draught came under the door and stirred the papers.",
    "The market stalls were closing, their awnings flapping in the wind.",
    "Two fishwives argued about the price of salt.",
    "The church clock was, as usual, ten minutes slow.",
    "The window glass was thick and green and warped the street beyond it.",
    "A dog barked at the gulls and was ignored.",
    "Smoke from the smokehouse drifted low across the water.",
    "The shutters of the customs house were painted a faded blue.",
    "Rainwater dripped steadily from the eaves.",
    "The whole quay smelled of oranges from a cargo split open that morning.",
    "Far out, a single sail tacked against the wind.",
    "The ledger lay open at a page of careful, cramped figures.",
    "The fire had burned down to a red glow.",
    "Nobody spoke for a while.",
]
REPLIES = [
    '"Then we wait," said {N}.',
    '"I will believe it when I see it," {N} said.',
    '"Ask the harbour master," said {N}, "if you can find him sober."',
    '"Not tonight," {N} said quietly.',
    '"You worry too much," said {N}.',
    '"Write it down, or nobody will remember," said {N}.',
]
HEDGES = [
    "In the bad light, {N}'s eyes seemed almost {v}.",
    "For a moment {N}'s eyes looked nearly {v} in the lamplight.",
    "In the fog, {N}'s eyes appeared almost {v}.",
    "Reflected in the water, {N}'s eyes seemed {v}, or perhaps that was the sky.",
]
RUMOURS = [
    '"I always heard {N} had {v} eyes," said {O}, squinting.',
    '"Someone told me {N} has {v} eyes," {O} said.',
    '"Didn\'t {N} have {v} eyes?" asked {O}.',
]

PRONOUNS = {
    "she": {"s": "she", "o": "her", "p": "her"},
    "he": {"s": "he", "o": "him", "p": "his"},
    "they": {"s": "they", "o": "them", "p": "their"},
}

FIRST_SYL = [
    "Ma",
    "Te",
    "Or",
    "Ka",
    "Li",
    "Bra",
    "Se",
    "Da",
    "Fe",
    "Ro",
    "Ve",
    "Ha",
    "Ni",
    "Jo",
    "Wy",
    "Ca",
    "Ari",
    "Ele",
    "Isa",
    "Tho",
]
FIRST_END = [
    "ra",
    "lis",
    "wen",
    "ric",
    "na",
    "mo",
    "dan",
    "set",
    "lin",
    "vik",
    "rin",
    "tha",
    "bel",
    "nor",
    "sa",
    "ko",
    "ven",
    "dra",
]
SUR_A = ["Ven", "Hal", "Cor", "Ash", "Mar", "Tal", "Bri", "Wex", "Dun", "Fal", "Gar", "Lon"]
SUR_B = ["ner", "row", "well", "by", "ton", "mere", "wick", "ford", "ley", "holt", "shaw"]
PLACE_A = [
    "Salt",
    "Dusk",
    "Ash",
    "Iron",
    "Gull",
    "Thorn",
    "Wren",
    "Cold",
    "Mill",
    "Black",
    "Hollow",
    "Kings",
]
PLACE_B = ["mere", "ford", "wick", "haven", "stead", "holm", "gate", "moor", "well", "port"]
NUM_WORDS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_words(n: int) -> str:
    if n < 20:
        return NUM_WORDS[n]
    tens, ones = divmod(n, 10)
    return TENS[tens] + ("" if ones == 0 else "-" + NUM_WORDS[ones])


@dataclass
class Person:
    id: str
    name: str
    first: str
    pronoun: str
    eye: str
    hair: str
    hand: str
    birthplace: str
    birth_day: int
    alias: str | None = None
    cannot: dict[str, int | None] = field(
        default_factory=dict
    )  # skill -> day learned (None: never)
    death_day: int | None = None
    death_chapter: int | None = None
    last_place: str | None = None
    last_day: int | None = None
    sheet: dict[str, str] = field(default_factory=dict)

    def pr(self, key: str) -> str:
        return PRONOUNS[self.pronoun][key]

    def age(self, day: int) -> int:
        return int((day - self.birth_day) / DAYS_PER_YEAR)


@dataclass
class Sentence:
    text: str
    tag: str | None = None


class ChapterText:
    """Accumulates paragraphs of sentences and resolves tagged sentences to body offsets."""

    def __init__(self) -> None:
        self.paragraphs: list[list[Sentence]] = []

    def add(self, *sentences: Sentence | str) -> None:
        self.paragraphs.append([s if isinstance(s, Sentence) else Sentence(s) for s in sentences])

    def render(self) -> tuple[str, dict[str, tuple[int, int, str]]]:
        parts: list[str] = []
        spans: dict[str, tuple[int, int, str]] = {}
        pos = 0
        for pi, para in enumerate(self.paragraphs):
            if pi:
                parts.append("\n\n")
                pos += 2
            for si, sent in enumerate(para):
                if si:
                    parts.append(" ")
                    pos += 1
                if sent.tag:
                    spans[sent.tag] = (pos, pos + len(sent.text), sent.text)
                parts.append(sent.text)
                pos += len(sent.text)
        return "".join(parts), spans


@dataclass
class Chapter:
    number: int
    title: str
    day: int | None
    label: str
    place: str
    flashback: bool
    text: ChapterText = field(default_factory=ChapterText)
    cast: list[Person] = field(default_factory=list)


class Generator:
    def __init__(self, seed: int, chapters: int):
        if chapters < 3:
            raise ValueError("need at least 3 chapters")
        self.seed = seed
        self.n = chapters
        self.rng = random.Random(seed)
        self.tag_counter = 0
        self.facts: list[dict] = []  # every mention of a character attribute
        self.contradictions: list[dict] = []
        self.negatives: list[dict] = []
        self.foreshadowing: list[dict] = []
        self.causal: list[dict] = []
        self.rule_mentions: list[dict] = []

    # ---- helpers -------------------------------------------------------------------------

    def tag(self) -> str:
        self.tag_counter += 1
        return f"t{self.tag_counter}"

    def pick(self, seq):
        return seq[self.rng.randrange(len(seq))]

    def fill(self, template: str, p: Person, **extra) -> str:
        values = {"N": p.first, "FULL": p.name, "s": p.pr("s"), "o": p.pr("o"), "p": p.pr("p")}
        values.update(extra)
        text = template.format(**values)
        return text[0].upper() + text[1:]

    # ---- world -------------------------------------------------------------------------------

    def build_world(self) -> None:
        rng = self.rng
        n_places = 8
        names: list[str] = []
        while len(names) < n_places:
            name = self.pick(PLACE_A) + self.pick(PLACE_B)
            if name not in names:
                names.append(name)
        self.places = names
        self.coords = {p: (rng.uniform(0, 100), rng.uniform(0, 100)) for p in names}

        n_people = min(48, max(6, self.n // 6 + 4))
        firsts: list[str] = []
        while len(firsts) < n_people:
            f = self.pick(FIRST_SYL) + self.pick(FIRST_END)
            if f not in firsts and not any(f in o or o in f for o in firsts):
                firsts.append(f)
        aliases = [
            "the Warden",
            "the Captain",
            "the Harbourmaster",
            "the Ferryman",
            "the Doctor",
            "the Archivist",
        ]
        self.people: list[Person] = []
        for i, first in enumerate(firsts):
            sur = self.pick(SUR_A) + self.pick(SUR_B)
            p = Person(
                id=f"P{i + 1}",
                name=f"{first} {sur}",
                first=first,
                pronoun=rng.choices(["she", "he", "they"], weights=[45, 45, 10])[0],
                eye=self.pick(EYE),
                hair=self.pick(HAIR),
                hand=rng.choices(HANDS, weights=[25, 75])[0],
                birthplace=self.pick(self.places),
                birth_day=-int(rng.uniform(18, 60) * DAYS_PER_YEAR),
                alias=aliases[i] if i < len(aliases) else None,
            )
            for skill in SKILLS:
                if rng.random() < 0.25:
                    p.cannot[skill] = None  # learning day is decided while simulating
            # Character-sheet canon for some attributes (what canon_conflict checks against).
            for attr, value in (
                ("eye_color", p.eye),
                ("hair_color", p.hair),
                ("handedness", p.hand),
                ("birthplace", p.birthplace),
            ):
                if rng.random() < 0.35:
                    p.sheet[attr] = value
            self.people.append(p)

    def travel_days(self, a: str, b: str) -> int:
        if a == b:
            return 0
        (x1, y1), (x2, y2) = self.coords[a], self.coords[b]
        return max(1, math.ceil(math.hypot(x1 - x2, y1 - y2) / 15))

    # ---- chapter skeletons ---------------------------------------------------------------------

    def plan_chapters(self) -> list[Chapter]:
        rng = self.rng
        chapters: list[Chapter] = []
        day = 0
        for number in range(1, self.n + 1):
            r = rng.random()
            flashback = number > 3 and r < 0.04
            unknown = number > 3 and 0.04 <= r < 0.08
            if number > 1 and not flashback:
                day += (
                    rng.choice([1, 1, 2, 3, 5, 8, 13])
                    if rng.random() > 0.03
                    else int(DAYS_PER_YEAR * rng.choice([2, 3, 5]))
                )
            if flashback:
                chap_day: int | None = max(
                    -int(DAYS_PER_YEAR * 10), day - int(DAYS_PER_YEAR * rng.choice([4, 6, 9]))
                )
                label = "Years earlier"
            elif unknown:
                chap_day = None
                label = "Undated interlude"
            else:
                chap_day = day
                label = f"Day {day}"
            chapters.append(
                Chapter(
                    number=number,
                    title=f"Chapter {number}",
                    day=chap_day,
                    label=label,
                    place=self.pick(self.places),
                    flashback=flashback,
                )
            )
        return chapters

    # ---- mentions ---------------------------------------------------------------------------

    ATTR_TEMPLATES = {
        "eye_color": [
            ("name_were", "{N}'s eyes were {v}."),
            ("name_had", "{N} had {v} eyes and a habit of watching doors."),
            ("no_mistaking", "There was no mistaking {N}'s {v} eyes."),
            ("pronoun", "{N} looked up, {p} {v} eyes narrowing against the light."),
            (
                "colour_of",
                "{N} had eyes the colour of {thing}.",
            ),
        ],
        "hair_color": [
            ("name_was", "{N}'s hair was {v}, tied back with a cord."),
            ("name_had", "{N} had {v} hair cut close to the skull."),
            ("pronoun", "{N} pushed {p} {v} hair out of {p} face."),
        ],
        "handedness": [
            ("name_was", "{N} was {v}-handed."),
            ("being", "Being {v}-handed, {N} kept the knife on the other side of the plate."),
            ("wrote_with", "{N} wrote with {p} {v} hand, as {s} always had."),
        ],
        "birthplace": [
            ("born_in", "{N} was born in {v}."),
            ("apposition", "{N}, born in {v}, knew every alley of the harbour."),
            ("grew_up", "{N} had grown up in {v}, where {s} was born."),
        ],
        "age": [
            ("was_n", "{N} was {v}, and felt every year of it."),
            ("year_old", "The {v}-year-old {N} took the stairs two at a time."),
            ("apposition", "{N}, {v}, had outlasted three harbour masters."),
            ("at_n", "At {v}, {N} had stopped expecting letters."),
        ],
    }
    COLOUR_THINGS = {
        "grey": "slate",
        "green": "sea glass",
        "blue": "deep water",
        "brown": "peat",
        "hazel": "river stones",
        "amber": "old honey",
    }

    def attr_sentence(
        self, p: Person, attr: str, value: str, day: int | None, template: str | None = None
    ) -> tuple[str, str]:
        choices = self.ATTR_TEMPLATES[attr]
        if attr == "eye_color" and value not in self.COLOUR_THINGS:
            choices = [c for c in choices if c[0] != "colour_of"]
        tid, tpl = next(c for c in choices if c[0] == template) if template else self.pick(choices)
        v = value
        if attr == "age":
            v = number_words(int(value)) if self.rng.random() < 0.7 else str(value)
        text = self.fill(tpl, p, v=v, thing=self.COLOUR_THINGS.get(value, "slate"))
        return text, tid

    def mention(
        self,
        ch: Chapter,
        p: Person,
        attr: str,
        value: str | None = None,
        template: str | None = None,
        kind: str = "asserted",
    ) -> tuple[Sentence, dict]:
        truth = {
            "eye_color": p.eye,
            "hair_color": p.hair,
            "handedness": p.hand,
            "birthplace": p.birthplace,
        }
        if value is None:
            value = str(p.age(ch.day)) if attr == "age" else truth[attr]
        text, tid = self.attr_sentence(p, attr, value, ch.day, template)
        tag = self.tag()
        fact = {
            "tag": tag,
            "chapter": ch.number,
            "subject": p.name,
            "predicate": attr,
            "value": value,
            "template": tid,
            "kind": kind,
            "day": ch.day,
        }
        self.facts.append(fact)  # kind "contradiction" marks deliberately wrong statements
        return Sentence(text, tag), fact

    # ---- simulation -------------------------------------------------------------------------

    def alive(self, p: Person, ch: Chapter) -> bool:
        if ch.day is None:
            return p.death_day is None
        return p.death_day is None or ch.day < p.death_day

    def can_be_at(self, p: Person, ch: Chapter) -> bool:
        if ch.day is None or ch.flashback or p.last_day is None or p.last_place is None:
            return True
        return ch.day - p.last_day >= self.travel_days(p.last_place, ch.place)

    def write(self, out: Path) -> dict:
        self.build_world()
        chapters = self.plan_chapters()
        rng = self.rng

        # Schedule one-off events by chapter.
        n = self.n
        deaths = rng.sample(range(n // 4, n - 1), k=min(len(self.people) // 4, max(1, n // 25)))
        rule_intro = {r["id"]: rng.randrange(1, max(2, n // 3)) for r in RULES}
        open_setups: list[dict] = []

        n_pos = max(6, n // 8)
        n_neg = max(6, n // 8)
        categories = ["identity", "canon", "age", "dead", "location", "ability", "rule"]
        pos_range = range(max(3, n // 5), n + 1)
        neg_range = range(2, n + 1)
        positive_chapters = sorted(rng.sample(pos_range, k=min(n_pos, len(pos_range))))
        negative_chapters = sorted(rng.sample(neg_range, k=min(n_neg, len(neg_range))))
        pos_kinds = {c: categories[i % len(categories)] for i, c in enumerate(positive_chapters)}
        neg_kinds_all = [
            "hedged",
            "dialogue",
            "memory",
            "learned_then_used",
            "rule_attempt",
            "feasible_travel",
            "dyed_hair",
        ]
        neg_kinds = {
            c: neg_kinds_all[i % len(neg_kinds_all)] for i, c in enumerate(negative_chapters)
        }

        for ch in chapters:
            t = ch.text.add
            # Opening: when and where.
            if ch.flashback:
                opening = f"Years earlier, in {ch.place}."
            elif ch.day is None:
                opening = f"Some time later, in {ch.place}."
            else:
                opening = f"{ch.label}, in {ch.place}."
            t(opening, self.pick(WEATHER))

            # Cast: alive characters who can reach this place.
            candidates = [p for p in self.people if self.alive(p, ch) and self.can_be_at(p, ch)]
            if len(candidates) < 2:
                candidates = [p for p in self.people if self.alive(p, ch)] or self.people[:2]
            ch.cast = rng.sample(candidates, k=min(len(candidates), rng.randint(2, 4)))

            for p in ch.cast:
                sentences: list[Sentence | str] = []
                if ch.day is not None and not ch.flashback and rng.random() < 0.35:
                    tag = self.tag()
                    sentences.append(
                        Sentence(
                            self.fill(
                                self.pick(
                                    [
                                        "{N} was in {P} that morning.",
                                        "{N} arrived in {P} before noon.",
                                        "By nightfall {N} had reached {P}.",
                                    ]
                                ),
                                p,
                                P=ch.place,
                            ),
                            tag,
                        )
                    )
                    self.facts.append(
                        {
                            "tag": tag,
                            "chapter": ch.number,
                            "subject": p.name,
                            "predicate": "location",
                            "value": ch.place,
                            "template": "location",
                            "kind": "asserted",
                            "day": ch.day,
                        }
                    )
                for _ in range(rng.randint(1, 2)):
                    sentences.append(self.fill("{N} " + self.pick(ACTIONS) + ".", p))
                if rng.random() < 0.45:
                    attr = self.pick(
                        ["eye_color", "hair_color", "handedness", "birthplace"]
                        + (["age"] if ch.day is not None and not ch.flashback else [])
                    )
                    s, _ = self.mention(ch, p, attr)
                    sentences.append(s)
                if rng.random() < 0.3:
                    sentences.append(self.fill(self.pick(SPEECH), p))
                t(*sentences)
                if ch.day is not None and not ch.flashback:
                    p.last_place, p.last_day = ch.place, ch.day

            # Scene filler and a short exchange of dialogue between two of the cast.
            for _ in range(rng.randint(1, 3)):
                t(*rng.sample(SCENE, k=rng.randint(2, 4)))
            if len(ch.cast) >= 2 and rng.random() < 0.6:
                a, b = ch.cast[0], ch.cast[1]
                t(self.fill(self.pick(SPEECH), a), self.fill(self.pick(REPLIES), b))

            # Skills: state inability early, learn later.
            for p in ch.cast:
                for skill, learned in list(p.cannot.items()):
                    if learned is None and ch.day is not None and not ch.flashback:
                        if not any(
                            f.get("skill") == skill and f["subject"] == p.name for f in self.facts
                        ):
                            tag = self.tag()
                            t(Sentence(self.fill(self.pick(SKILLS[skill][0]), p), tag))
                            self.facts.append(
                                {
                                    "tag": tag,
                                    "chapter": ch.number,
                                    "subject": p.name,
                                    "predicate": "ability",
                                    "skill": skill,
                                    "value": "cannot",
                                    "template": "cannot",
                                    "kind": "asserted",
                                    "day": ch.day,
                                }
                            )
                        elif rng.random() < 0.08:
                            tag = self.tag()
                            t(Sentence(self.fill(self.pick(SKILLS[skill][1]), p), tag))
                            p.cannot[skill] = ch.day
                            self.facts.append(
                                {
                                    "tag": tag,
                                    "chapter": ch.number,
                                    "subject": p.name,
                                    "predicate": "ability",
                                    "skill": skill,
                                    "value": "learned",
                                    "template": "learned",
                                    "kind": "asserted",
                                    "day": ch.day,
                                }
                            )

            # World rules are stated once, early.
            for rule in RULES:
                if rule_intro[rule["id"]] == ch.number:
                    p = ch.cast[0]
                    tag = self.tag()
                    t(
                        Sentence(
                            self.fill(
                                "{N} knew, as everyone in town knew, that "
                                + rule["statement"]
                                + ".",
                                p,
                            ),
                            tag,
                        )
                    )
                    self.rule_mentions.append(
                        {"tag": tag, "rule": rule["id"], "chapter": ch.number, "kind": "statement"}
                    )

            # Foreshadowing: set up, and later pay off most of them.
            if rng.random() < 0.12 and ch.cast:
                obj, payoff = FORESHADOW[len(self.foreshadowing) % len(FORESHADOW)]
                p = ch.cast[0]
                tag = self.tag()
                t(
                    Sentence(
                        self.fill(
                            "{N} noticed " + obj + ", and wondered about it for the "
                            "rest of the day.",
                            p,
                        ),
                        tag,
                    )
                )
                item = {
                    "id": f"F{len(self.foreshadowing) + 1}",
                    "setup_tag": tag,
                    "setup_chapter": ch.number,
                    "object": obj,
                    "payoff": payoff,
                    "resolved": False,
                    "subject": p.name,
                }
                self.foreshadowing.append(item)
                if rng.random() < 0.7:
                    open_setups.append(item)
            elif open_setups and rng.random() < 0.15 and ch.cast and not ch.flashback:
                item = open_setups.pop(0)
                if item["setup_chapter"] < ch.number:
                    p = ch.cast[0]
                    tag = self.tag()
                    t(Sentence(self.fill("{N} finally " + item["payoff"] + ".", p), tag))
                    item.update({"resolved": True, "payoff_tag": tag, "payoff_chapter": ch.number})

            # Causal links: cause and effect in one sentence.
            if rng.random() < 0.1 and ch.cast:
                cause, effect = self.pick(CAUSES)
                p = ch.cast[0]
                tag = self.tag()
                cause_text = cause.format(P=ch.place)  # starts lowercase ("the bridge ...")
                effect_text = self.fill(effect, p, P=ch.place)  # starts with a name
                t(Sentence(f"Because {cause_text}, {effect_text}.", tag))
                self.causal.append(
                    {"tag": tag, "chapter": ch.number, "cause": cause_text, "effect": effect_text}
                )

            # Deaths.
            if ch.number - 1 in deaths and ch.day is not None and not ch.flashback:
                p = ch.cast[-1]
                if p.death_day is None:
                    tag = self.tag()
                    t(
                        Sentence(
                            self.fill(
                                "{N} died " + self.pick(DEATH_CAUSES) + " in {P}.", p, P=ch.place
                            ),
                            tag,
                        )
                    )
                    p.death_day, p.death_chapter = ch.day, ch.number
                    self.facts.append(
                        {
                            "tag": tag,
                            "chapter": ch.number,
                            "subject": p.name,
                            "predicate": "death",
                            "value": ch.place,
                            "template": "death",
                            "kind": "asserted",
                            "day": ch.day,
                        }
                    )

            if ch.number in pos_kinds:
                self.inject_positive(ch, pos_kinds[ch.number], chapters)
            if ch.number in neg_kinds:
                self.inject_negative(ch, neg_kinds[ch.number], chapters)
            if ch.flashback:
                # Every flashback that can show a character who dies later in the story does.
                self.inject_negative(ch, "flashback_alive", chapters)

            t(self.pick(WEATHER), self.fill("{N} " + self.pick(ACTIONS) + ".", ch.cast[0]))

        return self.emit(out, chapters)

    # ---- injected contradictions ---------------------------------------------------------------

    def earlier_mention(self, p: Person, attr: str, before: int) -> dict | None:
        for f in self.facts:
            if (
                f["subject"] == p.name
                and f["predicate"] == attr
                and f["chapter"] < before
                and f["kind"] == "asserted"
            ):
                return f
        return None

    def record(
        self,
        category: str,
        kind: str,
        subject: str,
        predicate: str,
        tags: list[str],
        note: str,
        rule: str | None = None,
    ) -> None:
        self.contradictions.append(
            {
                "id": f"GT{len(self.contradictions) + 1}",
                "category": category,
                "kind": kind,
                "subject": subject,
                "predicate": predicate,
                "tags": tags,
                "note": note,
                **({"rule": rule} if rule else {}),
            }
        )

    def inject_positive(self, ch: Chapter, kind: str, chapters: list[Chapter]) -> None:
        dated = ch.day is not None and not ch.flashback
        if kind in ("age", "location", "dead", "ability") and not dated:
            kind = "identity"
        if kind == "identity" or kind == "canon":
            want_canon = kind == "canon"
            pool = [
                p
                for p in ch.cast
                if any(
                    (a in p.sheet) == want_canon
                    for a in ("eye_color", "hair_color", "handedness", "birthplace")
                )
            ]
            if not pool:
                pool = ch.cast
            p = self.pick(pool)
            attrs = [
                a
                for a in ("eye_color", "hair_color", "handedness", "birthplace")
                if (a in p.sheet) == want_canon
            ] or ["eye_color"]
            attr = self.pick(attrs)
            truth = {
                "eye_color": p.eye,
                "hair_color": p.hair,
                "handedness": p.hand,
                "birthplace": p.birthplace,
            }[attr]
            options = {
                "eye_color": EYE,
                "hair_color": HAIR,
                "handedness": HANDS,
                "birthplace": self.places,
            }[attr]
            wrong = self.pick([o for o in options if o != truth])
            tags = []
            if attr not in p.sheet:
                prior = self.earlier_mention(p, attr, ch.number)
                if prior is None:
                    # Make sure the conflict has an earlier, correct statement to conflict with.
                    first = next(
                        c
                        for c in chapters
                        if c.number < ch.number
                        and (c.day is None or p.death_day is None or c.day < p.death_day)
                    )
                    s, prior = self.mention(first, p, attr)
                    first.text.add(s)
                tags.append(prior["tag"])
            s, fact = self.mention(ch, p, attr, value=wrong, kind="contradiction")
            ch.text.add(s)
            tags.append(fact["tag"])
            in_sheet = attr in p.sheet
            self.record(
                "identity",
                "canon_conflict" if in_sheet else "attribute_conflict",
                p.name,
                attr,
                tags,
                f"{attr} '{wrong}' contradicts "
                + ("the character sheet" if in_sheet else "an earlier statement")
                + f" ('{truth}').",
            )
        elif kind == "age":
            p = self.pick(ch.cast)
            true_age = p.age(ch.day)
            prior = self.earlier_mention(p, "age", ch.number)
            if prior is None:
                first = next(
                    (
                        c
                        for c in chapters
                        if c.number < ch.number and c.day is not None and not c.flashback
                    ),
                    None,
                )
                if first is None:
                    return self.inject_positive(ch, "identity", chapters)
                s, prior = self.mention(first, p, "age")
                first.text.add(s)
            wrong = true_age + self.pick([-7, -5, -4, 4, 5, 8])
            s, fact = self.mention(ch, p, "age", value=str(max(1, wrong)), kind="contradiction")
            ch.text.add(s)
            self.record(
                "timeline",
                "age_timeline",
                p.name,
                "age",
                [prior["tag"], fact["tag"]],
                f"Age {wrong} on day {ch.day}; should be about {true_age}.",
            )
        elif kind == "dead":
            dead = [p for p in self.people if p.death_day is not None and p.death_day < ch.day]
            if not dead:
                return self.inject_positive(ch, "ability", chapters)
            p = self.pick(dead)
            death = next(
                f for f in self.facts if f["predicate"] == "death" and f["subject"] == p.name
            )
            tag = self.tag()
            ch.text.add(
                Sentence(
                    self.fill("{N} was in {P} that morning, alive and arguing.", p, P=ch.place), tag
                )
            )
            self.record(
                "timeline",
                "dead_character_active",
                p.name,
                "death",
                [death["tag"], tag],
                f"{p.name} died on day {p.death_day} but appears on day {ch.day}.",
            )
        elif kind == "location":
            p = self.pick(ch.cast)
            far = [pl for pl in self.places if self.travel_days(pl, ch.place) >= 3]
            if not far:
                return self.inject_positive(ch, "identity", chapters)
            other = self.pick(far)
            tag1, tag2 = self.tag(), self.tag()
            ch.text.add(
                Sentence(self.fill("{N} was in {P} that morning.", p, P=ch.place), tag1),
                Sentence(self.fill("By evening {N} was in {Q}.", p, Q=other), tag2),
            )
            self.record(
                "location",
                "location_conflict",
                p.name,
                "location",
                [tag1, tag2],
                f"{p.name} is in {ch.place} and {other} on day {ch.day}.",
            )
        elif kind == "ability":
            pool = [
                (p, s)
                for p in ch.cast
                for s, learned in p.cannot.items()
                if learned is None
                and any(
                    f.get("skill") == s and f["subject"] == p.name and f["chapter"] < ch.number
                    for f in self.facts
                )
            ]
            if not pool:
                return self.inject_positive(ch, "rule", chapters)
            p, skill = self.pick(pool)
            cannot = next(
                f for f in self.facts if f.get("skill") == skill and f["subject"] == p.name
            )
            tag = self.tag()
            ch.text.add(Sentence(self.fill(self.pick(SKILLS[skill][2]), p), tag))
            self.record(
                "abilities",
                "ability_conflict",
                p.name,
                skill,
                [cannot["tag"], tag],
                f"{p.name} cannot {skill} and has not learned, but does it here.",
            )
        elif kind == "rule":
            stated = [
                m
                for m in self.rule_mentions
                if m["kind"] == "statement" and m["chapter"] < ch.number
            ]
            if not stated:
                return self.inject_positive(ch, "identity", chapters)
            m = self.pick(stated)
            rule = next(r for r in RULES if r["id"] == m["rule"])
            p = self.pick(ch.cast)
            tag = self.tag()
            ch.text.add(Sentence(self.fill(rule["violation"], p), tag))
            self.rule_mentions.append(
                {"tag": tag, "rule": rule["id"], "chapter": ch.number, "kind": "violation"}
            )
            self.record(
                "world_rules",
                "world_rule_violation",
                rule["id"],
                "rule",
                [m["tag"], tag],
                f"Violates rule {rule['id']}: {rule['statement']}.",
                rule=rule["id"],
            )

    # ---- injected negatives ----------------------------------------------------------------

    def negative(self, kind: str, subject: str, predicate: str, tags: list[str], note: str) -> None:
        self.negatives.append(
            {
                "id": f"N{len(self.negatives) + 1}",
                "kind": kind,
                "subject": subject,
                "predicate": predicate,
                "tags": tags,
                "note": note,
            }
        )

    def inject_negative(self, ch: Chapter, kind: str, chapters: list[Chapter]) -> None:
        p = self.pick(ch.cast)
        other = next((q for q in ch.cast if q is not p), p)
        if kind == "hedged":
            wrong = self.pick([e for e in EYE if e != p.eye])
            tag = self.tag()
            ch.text.add(Sentence(self.fill(self.pick(HEDGES), p, v=wrong), tag))
            self.negative(
                kind, p.name, "eye_color", [tag], "Hedged perception, not a statement of fact."
            )
        elif kind == "dialogue":
            wrong = self.pick([e for e in EYE if e != p.eye])
            tag = self.tag()
            ch.text.add(Sentence(self.fill(self.pick(RUMOURS), p, v=wrong, O=other.first), tag))
            self.negative(
                kind, p.name, "eye_color", [tag], "A character's (wrong) words inside dialogue."
            )
        elif kind == "memory":
            dead = [
                q
                for q in self.people
                if q.death_day is not None and ch.day is not None and q.death_day < ch.day
            ]
            if not dead:
                return self.inject_negative(ch, "hedged", chapters)
            q = self.pick(dead)
            tag = self.tag()
            ch.text.add(
                Sentence(
                    self.fill(
                        "{N} remembered how {M} used to laugh at the harbour bell.", p, M=q.first
                    ),
                    tag,
                )
            )
            self.negative(
                kind, q.name, "death", [tag], "A dead character is remembered, not present."
            )
        elif kind == "learned_then_used":
            pool = [
                (q, s)
                for q in ch.cast
                for s, d in q.cannot.items()
                if d is not None and ch.day is not None and d < ch.day
            ]
            if not pool:
                return self.inject_negative(ch, "rule_attempt", chapters)
            q, skill = self.pick(pool)
            tag = self.tag()
            ch.text.add(Sentence(self.fill(self.pick(SKILLS[skill][2]), q), tag))
            self.negative(
                kind,
                q.name,
                skill,
                [tag],
                f"{q.name} learned to {skill} on day {q.cannot[skill]}; using it later "
                "is consistent.",
            )
        elif kind == "rule_attempt":
            stated = [m for m in self.rule_mentions if m["kind"] == "statement"]
            if not stated:
                return self.inject_negative(ch, "hedged", chapters)
            chosen = self.pick(stated)["rule"]
            rule = next(r for r in RULES if r["id"] == chosen)
            tag = self.tag()
            ch.text.add(Sentence(self.fill(rule["attempt"], p), tag))
            self.negative(
                kind,
                rule["id"],
                "rule",
                [tag],
                "A failed attempt confirms the rule rather than breaking it.",
            )
        elif kind == "feasible_travel":
            if ch.day is None or ch.flashback:
                return self.inject_negative(ch, "hedged", chapters)
            near = [
                pl for pl in self.places if pl != ch.place and self.travel_days(pl, ch.place) <= 2
            ]
            if not near:
                return self.inject_negative(ch, "hedged", chapters)
            dest = self.pick(near)
            d = self.travel_days(dest, ch.place)
            tag = self.tag()
            ch.text.add(
                Sentence(
                    self.fill(
                        "{d} days later {N} was in {Q}.",
                        p,
                        d=number_words(d + 1).capitalize(),
                        Q=dest,
                    ),
                    tag,
                )
            )
            self.negative(
                kind,
                p.name,
                "location",
                [tag],
                "Travel between the two places is possible in the time given.",
            )
        elif kind == "flashback_alive":
            # Died earlier in chapter order, but this flashback is set before the death.
            dead = [
                q
                for q in self.people
                if q.death_chapter is not None
                and q.death_chapter < ch.number
                and ch.day is not None
                and q.death_day is not None
                and ch.day < q.death_day
            ]
            if not dead:
                return
            q = self.pick(dead)
            tag = self.tag()
            ch.text.add(Sentence(self.fill("{N} was alive then, and laughing.", q), tag))
            self.negative(
                kind, q.name, "death", [tag], "A flashback set before the character's death."
            )
        elif kind == "dyed_hair":
            pool = [q for q in ch.cast if "hair_color" not in q.sheet]
            if not pool:
                return self.inject_negative(ch, "hedged", chapters)
            p = self.pick(pool)
            new = self.pick([h for h in HAIR if h != p.hair])
            tag1, tag2 = self.tag(), self.tag()
            ch.text.add(
                Sentence(self.fill("That week {N} dyed {p} hair {v}.", p, v=new), tag1),
                Sentence(self.fill("{N}'s hair was {v} now.", p, v=new), tag2),
            )
            p.hair = new
            self.negative(
                kind,
                p.name,
                "hair_color",
                [tag1, tag2],
                "An explicit change (dyed hair), not an inconsistency.",
            )

    # ---- output -----------------------------------------------------------------------------

    def emit(self, out: Path, chapters: list[Chapter]) -> dict:
        out.mkdir(parents=True, exist_ok=True)
        spans: dict[str, dict] = {}
        files = []
        for ch in chapters:
            body, tag_spans = ch.text.render()
            for tag, (s, e, text) in tag_spans.items():
                spans[tag] = {"chapter": ch.number, "start": s, "end": e, "text": text}
            fm = {
                "number": ch.number,
                "title": ch.title,
                "story_day": ch.day,
                "story_time_label": ch.label,
            }
            name = f"ch{ch.number:04d}.md"
            (out / name).write_text(
                "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + body + "\n",
                encoding="utf-8",
            )
            files.append(name)

        def ev(tags: list[str]) -> list[dict]:
            return [dict(spans[t]) for t in tags]

        characters = [
            {
                "name": p.name,
                "aliases": [p.alias] if p.alias else [],
                "description": f"Pronouns: {p.pronoun}/{p.pr('o')}.",
                "attributes": dict(p.sheet),
            }
            for p in self.people
        ]
        (out / "novel.yaml").write_text(
            yaml.safe_dump(
                {
                    "slug": f"syn-{self.n}-s{self.seed}",
                    "title": f"Synthetic Saltmere ({self.n} chapters, seed {self.seed})",
                    "synopsis": "Generated by novelforge.bench.generate for the benchmark.",
                    "characters": characters,
                    "chapters": files,
                },
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

        facts = [
            {**{k: v for k, v in f.items() if k != "tag"}, "evidence": ev([f["tag"]])}
            for f in self.facts
        ]
        gt = {
            "generator": {
                "name": "novelforge.bench.generate",
                "version": 1,
                "seed": self.seed,
                "chapters": self.n,
            },
            "contradictions": [
                {
                    **{k: v for k, v in c.items() if k != "tags"},
                    "m1_detectable": None,
                    "evidence": ev(c["tags"]),
                }
                for c in self.contradictions
            ],
            "negatives": [
                {**{k: v for k, v in n.items() if k != "tags"}, "evidence": ev(n["tags"])}
                for n in self.negatives
            ],
            "facts": facts,
            "queries": self.queries(facts),
            "foreshadowing": [
                {
                    "id": f["id"],
                    "subject": f["subject"],
                    "object": f["object"],
                    "resolved": f["resolved"],
                    "setup": ev([f["setup_tag"]])[0],
                    **({"payoff": ev([f["payoff_tag"]])[0]} if f["resolved"] else {}),
                }
                for f in self.foreshadowing
            ],
            "causal_links": [
                {
                    "chapter": c["chapter"],
                    "cause": c["cause"],
                    "effect": c["effect"],
                    "evidence": ev([c["tag"]])[0],
                }
                for c in self.causal
            ],
            "world_rules": [{"id": r["id"], "statement": r["statement"]} for r in RULES],
        }
        (out / "ground_truth.yaml").write_text(
            yaml.safe_dump(gt, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8"
        )
        return gt

    # ---- retrieval queries ----------------------------------------------------------------------

    QUERY_TEMPLATES = {
        "eye_color": [
            ("lexical", "What colour are {N}'s eyes?"),
            ("paraphrase", "How would you describe {N}'s gaze?"),
        ],
        "hair_color": [
            ("lexical", "What colour is {N}'s hair?"),
            ("paraphrase", "What does {N}'s hairstyle look like?"),
        ],
        "handedness": [
            ("lexical", "Is {N} left-handed or right-handed?"),
            ("paraphrase", "Which hand does {N} favour when writing?"),
        ],
        "birthplace": [
            ("lexical", "Where was {N} born?"),
            ("paraphrase", "What is {N}'s hometown?"),
        ],
        "age": [("lexical", "How old is {N}?"), ("paraphrase", "What is {N}'s age in years?")],
        "death": [
            ("lexical", "How did {N} die?"),
            ("paraphrase", "What happened to {N} at the end of {p} life?"),
        ],
        "location": [
            ("lexical", "When did {N} arrive in {V}?"),
            ("paraphrase", "On what day was {N} seen in {V}?"),
        ],
        "ability": [
            ("lexical", "Can {N} {S}?"),
            ("paraphrase", "Is {N} able to {S}, or did {s} learn later?"),
        ],
    }

    def queries(self, facts: list[dict]) -> list[dict]:
        rng = random.Random(self.seed * 7919 + 1)
        people = {p.name: p for p in self.people}
        groups: dict[tuple, list[dict]] = {}
        for f in facts:
            key = (
                f["subject"],
                f["predicate"],
                f.get("skill"),
                f["value"] if f["predicate"] == "location" else None,
            )
            groups.setdefault(key, []).append(f)
        keys = list(groups)
        rng.shuffle(keys)
        out = []
        for key in keys[: max(40, min(400, len(keys)))]:
            subject, predicate, skill, place = key
            p = people[subject]
            for qkind, tpl in self.QUERY_TEMPLATES[predicate]:
                q = tpl.format(N=p.first, V=place or "", S=skill or "", p=p.pr("p"), s=p.pr("s"))
                out.append(
                    {
                        "id": f"Q{len(out) + 1}",
                        "kind": qkind,
                        "query": q,
                        "subject": subject,
                        "predicate": predicate,
                        "relevant": [e for f in groups[key] for e in f["evidence"]],
                    }
                )
        return out


def generate(out: Path, chapters: int, seed: int) -> dict:
    """Write a synthetic corpus to `out` and return its ground truth."""
    return Generator(seed=seed, chapters=chapters).write(out)
