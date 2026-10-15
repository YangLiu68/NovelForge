"""Load a sample novel folder (novel.yaml + markdown chapters with front matter).

IDs are derived with uuid5 from the novel slug, so importing the same files always produces
the same novel, chapter and character IDs.
"""

import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from novelforge.core.text import normalize_body

SAMPLE_NAMESPACE = uuid.UUID("0b8f7a52-5d0e-4f4e-8f63-2a8f7f0c4d11")


@dataclass(frozen=True)
class SampleCharacter:
    id: uuid.UUID
    name: str
    aliases: list[str]
    description: str
    attributes: dict[str, str]


@dataclass(frozen=True)
class SampleChapter:
    id: uuid.UUID
    number: int
    title: str
    body: str
    story_day: int | None
    story_time_label: str | None


@dataclass(frozen=True)
class SampleLocation:
    id: uuid.UUID
    name: str
    travel_days: dict[str, int]


@dataclass(frozen=True)
class SampleNovel:
    id: uuid.UUID
    slug: str
    title: str
    synopsis: str
    characters: list[SampleCharacter]
    chapters: list[SampleChapter]
    ground_truth: dict = field(default_factory=dict)
    locations: list[SampleLocation] = field(default_factory=list)


def _split_front_matter(text: str) -> tuple[dict, str]:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("unterminated front matter")
    return yaml.safe_load(text[4:end]) or {}, text[end + 5 :]


def available_samples(samples_dir: Path) -> list[str]:
    return sorted(p.parent.name for p in samples_dir.glob("*/novel.yaml"))


def load_sample(samples_dir: Path, name: str) -> SampleNovel:
    if name not in available_samples(samples_dir):
        raise FileNotFoundError(f"unknown sample '{name}'")
    return load_folder(samples_dir / name)


def load_folder(folder: Path) -> SampleNovel:
    """Load any folder with novel.yaml + chapter files (samples and generated corpora)."""
    if not (folder / "novel.yaml").exists():
        raise FileNotFoundError(f"{folder} has no novel.yaml")
    meta = yaml.safe_load((folder / "novel.yaml").read_text(encoding="utf-8"))
    slug = meta["slug"]

    def sid(kind: str, key: str) -> uuid.UUID:
        return uuid.uuid5(SAMPLE_NAMESPACE, f"{slug}/{kind}/{key}")

    characters = [
        SampleCharacter(
            id=sid("character", c["name"]),
            name=c["name"],
            aliases=list(c.get("aliases") or []),
            description=c.get("description", ""),
            attributes={k: str(v) for k, v in (c.get("attributes") or {}).items()},
        )
        for c in meta["characters"]
    ]
    chapters = []
    for filename in meta["chapters"]:
        fm, body = _split_front_matter((folder / filename).read_text(encoding="utf-8"))
        chapters.append(
            SampleChapter(
                id=sid("chapter", str(fm["number"])),
                number=int(fm["number"]),
                title=fm["title"],
                body=normalize_body(body),
                story_day=fm.get("story_day"),
                story_time_label=fm.get("story_time_label"),
            )
        )
    gt_path = folder / "ground_truth.yaml"
    ground_truth = yaml.safe_load(gt_path.read_text(encoding="utf-8")) if gt_path.exists() else {}
    locations = [
        SampleLocation(
            id=sid("location", loc["name"]),
            name=loc["name"],
            travel_days={k: int(v) for k, v in (loc.get("travel_days") or {}).items()},
        )
        for loc in meta.get("locations") or []
    ]
    return SampleNovel(
        locations=locations,
        id=sid("novel", slug),
        slug=slug,
        title=meta["title"],
        synopsis=meta.get("synopsis", ""),
        characters=characters,
        chapters=sorted(chapters, key=lambda c: c.number),
        ground_truth=ground_truth,
    )
