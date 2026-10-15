import uuid

from fastapi import Depends
from sqlalchemy.orm import Session

from novelforge.db import get_session
from novelforge.models import Chapter, Character, Novel
from novelforge.services.workspace import get_or_404

SessionDep = Depends(get_session)


def novel_dep(novel_id: uuid.UUID, session: Session = SessionDep) -> Novel:
    return get_or_404(session, Novel, novel_id, "Novel")


def chapter_dep(chapter_id: uuid.UUID, session: Session = SessionDep) -> Chapter:
    return get_or_404(session, Chapter, chapter_id, "Chapter")


def character_dep(character_id: uuid.UUID, session: Session = SessionDep) -> Character:
    return get_or_404(session, Character, character_id, "Character")
