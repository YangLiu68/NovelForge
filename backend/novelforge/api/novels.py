from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novelforge.api.deps import SessionDep, novel_dep
from novelforge.models import Chapter, Character, Novel
from novelforge.schemas import NovelCreate, NovelOut, NovelUpdate
from novelforge.services import workspace

router = APIRouter(prefix="/api/novels", tags=["novels"])


def _out(session: Session, novel: Novel) -> NovelOut:
    out = NovelOut.model_validate(novel)
    out.chapter_count = (
        session.scalar(
            select(func.count()).select_from(Chapter).where(Chapter.novel_id == novel.id)
        )
        or 0
    )
    out.character_count = (
        session.scalar(
            select(func.count()).select_from(Character).where(Character.novel_id == novel.id)
        )
        or 0
    )
    return out


@router.get("", response_model=list[NovelOut])
def list_novels(session: Session = SessionDep):
    novels = session.scalars(select(Novel).order_by(Novel.created_at, Novel.title)).all()
    return [_out(session, n) for n in novels]


@router.post("", response_model=NovelOut, status_code=status.HTTP_201_CREATED)
def create_novel(payload: NovelCreate, session: Session = SessionDep):
    novel = workspace.create_novel(session, payload.title, payload.synopsis)
    session.commit()
    return _out(session, novel)


@router.get("/{novel_id}", response_model=NovelOut)
def get_novel(novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    return _out(session, novel)


@router.patch("/{novel_id}", response_model=NovelOut)
def update_novel(
    payload: NovelUpdate, novel: Novel = Depends(novel_dep), session: Session = SessionDep
):
    fields = payload.model_dump(exclude_unset=True, exclude={"version"})
    workspace.update_novel(session, novel, payload.version, fields)
    session.commit()
    return _out(session, novel)


@router.delete("/{novel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_novel(novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    session.delete(novel)
    session.commit()
