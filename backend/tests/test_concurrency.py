"""The race the API-level version check cannot see: two writers that both read version 1."""

import pytest

from novelforge.db import get_sessionmaker
from novelforge.models import Chapter
from novelforge.services import workspace
from novelforge.services.errors import Conflict


def test_concurrent_writers_second_one_gets_conflict(database_url):
    maker = get_sessionmaker()
    with maker() as s:
        novel = workspace.create_novel(s, "N")
        chapter = workspace.create_chapter(s, novel, "One", "v1")
        s.commit()
        chapter_id = chapter.id

    a, b = maker(), maker()
    try:
        ch_a = a.get(Chapter, chapter_id)
        ch_b = b.get(Chapter, chapter_id)
        assert ch_a.version == ch_b.version == 1
        workspace.update_chapter(b, ch_b, 1, {"body": "writer B"})
        b.commit()
        with pytest.raises(Conflict) as exc:
            workspace.update_chapter(a, ch_a, 1, {"body": "writer A"})
        assert exc.value.current_version == 2
    finally:
        a.close()
        b.close()

    with maker() as s:
        final = s.get(Chapter, chapter_id)
        assert (final.body, final.version) == ("writer B", 2)
