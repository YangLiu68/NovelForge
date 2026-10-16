"""Chinese full-text search: passages with Chinese are indexed as character bigrams

Adds passage.search_text (null for text without Chinese) and recomputes the tsvector from
coalesce(search_text, text). Existing Chinese passages are backfilled.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-16 01:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _swap_tsv(expression: str) -> None:
    op.drop_index("ix_passage_tsv", table_name="passage", postgresql_using="gin")
    op.drop_column("passage", "tsv")
    op.add_column(
        "passage",
        sa.Column(
            "tsv", postgresql.TSVECTOR(), sa.Computed(expression, persisted=True), nullable=True
        ),
    )
    op.create_index("ix_passage_tsv", "passage", ["tsv"], unique=False, postgresql_using="gin")


def upgrade() -> None:
    from novelforge.core.text import cjk_search_text

    op.add_column("passage", sa.Column("search_text", sa.Text(), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, text FROM passage WHERE text ~ '[一-鿿]'")).fetchall()
    for pid, text in rows:
        conn.execute(
            sa.text("UPDATE passage SET search_text = :s WHERE id = :id"),
            {"s": cjk_search_text(text), "id": pid},
        )
    _swap_tsv("to_tsvector('english', coalesce(search_text, text))")


def downgrade() -> None:
    _swap_tsv("to_tsvector('english', text)")
    op.drop_column("passage", "search_text")
