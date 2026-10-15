from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from novelforge.api.deps import SessionDep, character_dep, novel_dep
from novelforge.models import Character, Novel
from novelforge.schemas import CharacterCreate, CharacterOut, CharacterUpdate
from novelforge.services import workspace

router = APIRouter(prefix="/api", tags=["characters"])


@router.get("/novels/{novel_id}/characters", response_model=list[CharacterOut])
def list_characters(novel: Novel = Depends(novel_dep), session: Session = SessionDep):
    return session.scalars(
        select(Character).where(Character.novel_id == novel.id).order_by(Character.name)
    ).all()


@router.post("/novels/{novel_id}/characters", response_model=CharacterOut,
             status_code=status.HTTP_201_CREATED)
def create_character(payload: CharacterCreate, novel: Novel = Depends(novel_dep),
                     session: Session = SessionDep):
    character = workspace.create_character(
        session, novel, payload.name, payload.aliases, payload.description, payload.attributes
    )
    session.commit()
    return character


@router.get("/characters/{character_id}", response_model=CharacterOut)
def get_character(character: Character = Depends(character_dep)):
    return character


@router.patch("/characters/{character_id}", response_model=CharacterOut)
def update_character(payload: CharacterUpdate, character: Character = Depends(character_dep),
                     session: Session = SessionDep):
    fields = payload.model_dump(exclude_unset=True, exclude={"version"})
    workspace.update_character(session, character, payload.version, fields)
    session.commit()
    return character


@router.delete("/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(character: Character = Depends(character_dep),
                     session: Session = SessionDep):
    workspace.delete_character(session, character)
    session.commit()
