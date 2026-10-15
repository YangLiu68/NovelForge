import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from novelforge.api.deps import SessionDep, chapter_dep, novel_dep
from novelforge.models import Chapter, Novel, Revision
from novelforge.schemas import (
    ChapterCreate,
    ChapterOut,
    ChapterSummary,
    ChapterUpdate,
    RevisionOut,
    RevisionSummary,
)
from novelforge.services import workspace
from novelforge.services.errors import NotFound

router = APIRouter(prefix="/api", tags=["chapters"])


def _summary(chapter: Chapter, cls=ChapterSummary):
    out = cls.model_validate(chapter)
    out.word_count = len(chapter.body.split())
    return out


@router.get("/novels/{novel_id}/chapters", response_model=list[ChapterSummary])
def list_chapters(novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    rows = session.scalars(
        select(Chapter).where(Chapter.novel_id == novel.id).order_by(Chapter.number)
    )
    return [_summary(c) for c in rows]


@router.post(
    "/novels/{novel_id}/chapters", response_model=ChapterOut, status_code=status.HTTP_201_CREATED
)
def create_chapter(
    payload: ChapterCreate, novel: Novel = Depends(novel_dep), session: Session = SessionDep
):
    chapter = workspace.create_chapter(
        session,
        novel,
        payload.title,
        payload.body,
        payload.number,
        payload.story_day,
        payload.story_time_label,
    )
    session.commit()
    return _summary(chapter, ChapterOut)


@router.get("/chapters/{chapter_id}", response_model=ChapterOut)
def get_chapter(chapter: Chapter = Depends(chapter_dep)):
    return _summary(chapter, ChapterOut)


@router.patch("/chapters/{chapter_id}", response_model=ChapterOut)
def update_chapter(
    payload: ChapterUpdate, chapter: Chapter = Depends(chapter_dep), session: Session = SessionDep
):
    fields = payload.model_dump(exclude_unset=True, exclude={"version"})
    workspace.update_chapter(session, chapter, payload.version, fields)
    session.commit()
    return _summary(chapter, ChapterOut)


@router.delete("/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chapter(chapter: Chapter = Depends(chapter_dep), session: Session = SessionDep):
    session.delete(chapter)
    session.commit()


@router.get("/chapters/{chapter_id}/revisions", response_model=list[RevisionSummary])
def list_revisions(chapter: Chapter = Depends(chapter_dep), session: Session = SessionDep):
    return session.scalars(
        select(Revision).where(Revision.chapter_id == chapter.id).order_by(Revision.version.desc())
    ).all()


@router.get("/chapters/{chapter_id}/revisions/{version}", response_model=RevisionOut)
def get_revision(version: int, chapter_id: uuid.UUID, session: Session = SessionDep):
    rev = session.scalar(
        select(Revision).where(Revision.chapter_id == chapter_id, Revision.version == version)
    )
    if rev is None:
        raise NotFound("Revision", f"{chapter_id}@{version}")
    return rev
