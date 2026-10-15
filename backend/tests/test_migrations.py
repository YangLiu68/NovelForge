from sqlalchemy import create_engine, inspect

from tests.conftest import drop_database, recreate_database

TABLES = {"novel", "chapter", "revision", "passage", "character", "claim", "evidence_span"}


def test_upgrade_and_downgrade_on_empty_database():
    from alembic import command

    from novelforge.cli import _alembic_config

    name = "novelforge_migration_test"
    url = recreate_database(name).render_as_string(hide_password=False)
    try:
        cfg = _alembic_config()
        cfg.attributes["url"] = url
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        assert set(inspect(engine).get_table_names()) >= TABLES
        command.downgrade(cfg, "base")
        assert not TABLES & set(inspect(engine).get_table_names())
        engine.dispose()
    finally:
        drop_database(name)
