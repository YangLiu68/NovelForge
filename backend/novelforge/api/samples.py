from fastapi import APIRouter
from sqlalchemy.orm import Session

from novelforge.api.deps import SessionDep
from novelforge.config import get_settings
from novelforge.core.sample import available_samples
from novelforge.schemas import ImportOut, SampleOut
from novelforge.services.errors import NotFound
from novelforge.services.importer import import_sample

router = APIRouter(prefix="/api/samples", tags=["samples"])


@router.get("", response_model=list[SampleOut])
def list_samples():
    return [{"name": n} for n in available_samples(get_settings().samples_dir)]


@router.post("/{name}/import", response_model=ImportOut)
def import_sample_route(name: str, session: Session = SessionDep):
    samples_dir = get_settings().samples_dir
    if name not in available_samples(samples_dir):
        raise NotFound("Sample", name)
    result = import_sample(session, samples_dir, name)
    session.commit()
    return {"novel_id": result.novel.id, "created": result.created}
