"""retrieval: pgvector embeddings, embedding cache, job queue

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("passage", sa.Column("text_hash", sa.String(length=64), nullable=True))
    op.execute("UPDATE passage SET text_hash = encode(sha256(convert_to(text, 'UTF8')), 'hex')")
    op.alter_column("passage", "text_hash", nullable=False)
    op.add_column("passage", sa.Column("embedding", Vector(), nullable=True))
    op.add_column("passage", sa.Column("embedding_model", sa.String(length=120), nullable=True))
    op.create_index("ix_passage_embedding_model", "passage", ["novel_id", "embedding_model"])

    op.create_table(
        "embedding_cache",
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("model", "text_hash"),
    )
    op.create_table(
        "job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=300), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "run_after", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_job_queue", "job", ["status", "run_after"])


def downgrade() -> None:
    op.drop_index("ix_job_queue", table_name="job")
    op.drop_table("job")
    op.drop_table("embedding_cache")
    # Per-model HNSW indexes created at runtime depend on passage.embedding.
    op.execute(
        "DO $$ DECLARE r record; BEGIN FOR r IN SELECT indexname FROM pg_indexes "
        "WHERE tablename = 'passage' AND indexname LIKE 'ix_passage_hnsw_%' LOOP "
        "EXECUTE 'DROP INDEX ' || quote_ident(r.indexname); END LOOP; END $$"
    )
    op.drop_index("ix_passage_embedding_model", table_name="passage")
    op.drop_column("passage", "embedding_model")
    op.drop_column("passage", "embedding")
    op.drop_column("passage", "text_hash")
