"""Create/update/delete operations for novels, chapters and characters.

Updates carry the version the client last saw. A mismatch raises Conflict before anything is
written; a concurrent writer that slips in between is caught by SQLAlchemy's version check
(UPDATE ... WHERE version = :seen) and also reported as Conflict.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from novelforge.core.text import content_hash, normalize_body
from novelforge.models import Chapter, Character, Novel, Revision
from novelforge.services.derived import rebuild_chapter, rebuild_novel_claims
from novelforge.services.errors import Conflict, NotFound


def get_or_404(session: Session, model: type, entity_id: uuid.UUID, label: str):
    obj = session.get(model, entity_id)
    if obj is None:
        raise NotFound(label, entity_id)
    return obj


def _check_version(obj: Any, expected: int, label: str) -> None:
    if obj.version != expected:
        raise Conflict(
            f"{label} was changed by someone else (you have version {expected}, "
            f"current is {obj.version}). Reload and reapply your edit.",
            current_version=obj.version,
        )


def _flush(session: Session, obj: Any, label: str) -> None:
    try:
        session.flush()
    except StaleDataError as exc:
        session.rollback()
        current = session.get(type(obj), obj.id)
        raise Conflict(
            f"{label} was changed by someone else. Reload and reapply your edit.",
            current_version=current.version if current else None,
        ) from exc
    except IntegrityError as exc:
        session.rollback()
        raise Conflict(f"{label} conflicts with an existing record: {exc.orig}") from exc


# Novels


def create_novel(session: Session, title: str, synopsis: str = "",
                 novel_id: uuid.UUID | None = None, slug: str | None = None) -> Novel:
    novel = Novel(id=novel_id or uuid.uuid4(), title=title, synopsis=synopsis, slug=slug)
    session.add(novel)
    _flush(session, novel, "Novel")
    return novel


def update_novel(session: Session, novel: Novel, version: int, fields: dict[str, Any]) -> Novel:
    _check_version(novel, version, "Novel")
    for key in ("title", "synopsis"):
        if key in fields:
            setattr(novel, key, fields[key])
    _flush(session, novel, "Novel")
    return novel


# Chapters


def _write_revision(session: Session, chapter: Chapter) -> None:
    session.add(
        Revision(chapter_id=chapter.id, version=chapter.version, title=chapter.title,
                 body=chapter.body, content_hash=chapter.content_hash)
    )


def create_chapter(
    session: Session, novel: Novel, title: str, body: str = "", number: int | None = None,
    story_day: int | None = None, story_time_label: str | None = None,
    chapter_id: uuid.UUID | None = None,
) -> Chapter:
    if number is None:
        current_max = session.scalar(
            select(func.max(Chapter.number)).where(Chapter.novel_id == novel.id)
        )
        number = (current_max or 0) + 1
    body = normalize_body(body)
    chapter = Chapter(
        id=chapter_id or uuid.uuid4(), novel_id=novel.id, number=number, title=title, body=body,
        story_day=story_day, story_time_label=story_time_label, content_hash=content_hash(body),
    )
    session.add(chapter)
    _flush(session, chapter, f"Chapter {number}")
    _write_revision(session, chapter)
    rebuild_chapter(session, chapter)
    return chapter


def update_chapter(session: Session, chapter: Chapter, version: int,
                   fields: dict[str, Any]) -> Chapter:
    _check_version(chapter, version, "Chapter")
    if "body" in fields:
        fields["body"] = normalize_body(fields["body"])
        fields["content_hash"] = content_hash(fields["body"])
    changed = False
    for key in ("title", "body", "number", "story_day", "story_time_label", "content_hash"):
        if key in fields and getattr(chapter, key) != fields[key]:
            setattr(chapter, key, fields[key])
            changed = True
    if not changed:
        return chapter
    _flush(session, chapter, "Chapter")  # bumps chapter.version
    _write_revision(session, chapter)
    rebuild_chapter(session, chapter)
    return chapter


# Characters


def create_character(
    session: Session, novel: Novel, name: str, aliases: list[str] | None = None,
    description: str = "", attributes: dict[str, str] | None = None,
    character_id: uuid.UUID | None = None, rebuild: bool = True,
) -> Character:
    character = Character(
        id=character_id or uuid.uuid4(), novel_id=novel.id, name=name.strip(),
        aliases=_clean_aliases(aliases or []), description=description,
        attributes=dict(attributes or {}),
    )
    session.add(character)
    _flush(session, character, f"Character '{name}'")
    if rebuild:
        rebuild_novel_claims(session, novel.id)
    return character


def update_character(session: Session, character: Character, version: int,
                     fields: dict[str, Any]) -> Character:
    _check_version(character, version, "Character")
    if "aliases" in fields:
        fields["aliases"] = _clean_aliases(fields["aliases"])
    if "name" in fields:
        fields["name"] = fields["name"].strip()
    changed = False
    for key in ("name", "aliases", "description", "attributes"):
        if key in fields and getattr(character, key) != fields[key]:
            setattr(character, key, fields[key])
            changed = True
    if not changed:
        return character
    _flush(session, character, "Character")
    rebuild_novel_claims(session, character.novel_id)
    return character


def delete_character(session: Session, character: Character) -> None:
    novel_id = character.novel_id
    session.delete(character)
    rebuild_novel_claims(session, novel_id)


def _clean_aliases(aliases: list[str]) -> list[str]:
    seen: list[str] = []
    for a in aliases:
        a = a.strip()
        if a and a not in seen:
            seen.append(a)
    return seen
