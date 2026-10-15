"""extraction review and canon

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15 01:02:43.157125
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "location",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("novel_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("travel_days", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["novel_id"], ["novel.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("novel_id", "name"),
    )
    op.create_table(
        "review_decision",
        sa.Column("novel_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=40), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["novel_id"], ["novel.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("novel_id", "fingerprint"),
    )
    op.create_table(
        "scene",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("novel_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start", sa.Integer(), nullable=False),
        sa.Column("end", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapter.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["novel_id"], ["novel.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chapter_id", "ordinal"),
    )
    op.create_table(
        "canon_change",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("novel_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_claim_id", sa.Uuid(), nullable=True),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["novel_id"], ["novel.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_claim_id"], ["claim.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_canon_change_novel", "canon_change", ["novel_id", "created_at"], unique=False
    )
    op.create_table(
        "plot_thread",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("novel_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("setup_chapter_id", sa.Uuid(), nullable=True),
        sa.Column("payoff_chapter_id", sa.Uuid(), nullable=True),
        sa.Column("source_claim_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["novel_id"], ["novel.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payoff_chapter_id"], ["chapter.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["setup_chapter_id"], ["chapter.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_claim_id"], ["claim.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "relationship",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("novel_id", sa.Uuid(), nullable=False),
        sa.Column("source_character_id", sa.Uuid(), nullable=False),
        sa.Column("target_character_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_claim_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["novel_id"], ["novel.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_character_id"], ["character.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_claim_id"], ["claim.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_character_id"], ["character.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("novel_id", "source_character_id", "target_character_id", "kind"),
    )
    op.create_table(
        "timeline_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("novel_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("subject_character_id", sa.Uuid(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("story_day", sa.Integer(), nullable=True),
        sa.Column("chapter_id", sa.Uuid(), nullable=True),
        sa.Column("source_claim_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapter.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["novel_id"], ["novel.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_claim_id"], ["claim.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subject_character_id"], ["character.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_timeline_novel_day", "timeline_event", ["novel_id", "story_day"], unique=False
    )
    op.create_table(
        "world_rule",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("novel_id", sa.Uuid(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_claim_id", sa.Uuid(), nullable=True),
        sa.Column("source_chapter_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["novel_id"], ["novel.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_chapter_id"], ["chapter.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_claim_id"], ["claim.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "claim",
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "claim", sa.Column("fingerprint", sa.String(length=40), nullable=False, server_default="")
    )
    op.add_column("claim", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("claim", sa.Column("review_note", sa.Text(), nullable=True))
    op.alter_column(
        "claim",
        "value",
        existing_type=sa.VARCHAR(length=200),
        type_=sa.String(length=500),
        existing_nullable=False,
    )
    op.alter_column(
        "claim",
        "raw_value",
        existing_type=sa.VARCHAR(length=200),
        type_=sa.String(length=500),
        existing_nullable=False,
    )
    op.alter_column(
        "claim",
        "extractor",
        existing_type=sa.VARCHAR(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.create_index("ix_claim_novel_status", "claim", ["novel_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_claim_novel_status", table_name="claim")
    op.alter_column(
        "claim",
        "extractor",
        existing_type=sa.String(length=64),
        type_=sa.VARCHAR(length=32),
        existing_nullable=False,
    )
    op.alter_column(
        "claim",
        "raw_value",
        existing_type=sa.String(length=500),
        type_=sa.VARCHAR(length=200),
        existing_nullable=False,
    )
    op.alter_column(
        "claim",
        "value",
        existing_type=sa.String(length=500),
        type_=sa.VARCHAR(length=200),
        existing_nullable=False,
    )
    op.drop_column("claim", "review_note")
    op.drop_column("claim", "reviewed_at")
    op.drop_column("claim", "fingerprint")
    op.drop_column("claim", "details")
    op.drop_table("world_rule")
    op.drop_index("ix_timeline_novel_day", table_name="timeline_event")
    op.drop_table("timeline_event")
    op.drop_table("relationship")
    op.drop_table("plot_thread")
    op.drop_index("ix_canon_change_novel", table_name="canon_change")
    op.drop_table("canon_change")
    op.drop_table("scene")
    op.drop_table("review_decision")
    op.drop_table("location")
