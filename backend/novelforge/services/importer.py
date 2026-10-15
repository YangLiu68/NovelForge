"""Deterministic import of a sample novel folder.

Importing is idempotent: if the novel already exists (same uuid5 id) nothing is written and
the existing novel is returned with created=False. Delete the novel to re-import it.
"""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from novelforge.core.sample import SampleNovel, load_folder, load_sample
from novelforge.models import Location, Novel
from novelforge.services import workspace


@dataclass
class ImportResult:
    novel: Novel
    created: bool


def import_sample(session: Session, samples_dir: Path, name: str) -> ImportResult:
    return import_novel(session, load_sample(samples_dir, name))


def import_folder(session: Session, folder: Path) -> ImportResult:
    return import_novel(session, load_folder(folder))


def import_novel(session: Session, sample: SampleNovel) -> ImportResult:
    existing = session.get(Novel, sample.id)
    if existing is not None:
        return ImportResult(existing, created=False)
    novel = workspace.create_novel(
        session, sample.title, sample.synopsis, novel_id=sample.id, slug=sample.slug
    )
    for c in sample.characters:
        workspace.create_character(
            session,
            novel,
            c.name,
            c.aliases,
            c.description,
            c.attributes,
            character_id=c.id,
            rebuild=False,
        )
    for loc in sample.locations:
        session.add(
            Location(id=loc.id, novel_id=novel.id, name=loc.name, travel_days=loc.travel_days)
        )
    for ch in sample.chapters:
        workspace.create_chapter(
            session,
            novel,
            ch.title,
            ch.body,
            ch.number,
            ch.story_day,
            ch.story_time_label,
            chapter_id=ch.id,
        )  # characters exist already, so each chapter's claims are extracted here
    return ImportResult(novel, created=True)
