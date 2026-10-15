"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-14 22:37:29.575586
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('novel',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('slug', sa.String(length=100), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('synopsis', sa.Text(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('chapter',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('novel_id', sa.Uuid(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('story_day', sa.Integer(), nullable=True),
    sa.Column('story_time_label', sa.String(length=200), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('number >= 1', name='chapter_number_positive'),
    sa.ForeignKeyConstraint(['novel_id'], ['novel.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('novel_id', 'number')
    )
    op.create_table('character',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('novel_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('aliases', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['novel_id'], ['novel.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('novel_id', 'name')
    )
    op.create_table('claim',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('novel_id', sa.Uuid(), nullable=False),
    sa.Column('chapter_id', sa.Uuid(), nullable=False),
    sa.Column('chapter_version', sa.Integer(), nullable=False),
    sa.Column('subject_character_id', sa.Uuid(), nullable=True),
    sa.Column('subject_text', sa.String(length=200), nullable=False),
    sa.Column('predicate', sa.String(length=64), nullable=False),
    sa.Column('value', sa.String(length=200), nullable=False),
    sa.Column('raw_value', sa.String(length=200), nullable=False),
    sa.Column('modality', sa.String(length=16), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('extractor', sa.String(length=32), nullable=False),
    sa.Column('effective_day', sa.Integer(), nullable=True),
    sa.Column('time_certainty', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(time_certainty = 'unknown' AND effective_day IS NULL) OR (time_certainty <> 'unknown' AND effective_day IS NOT NULL)", name='claim_time_consistent'),
    sa.ForeignKeyConstraint(['chapter_id'], ['chapter.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['novel_id'], ['novel.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subject_character_id'], ['character.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_claim_chapter', 'claim', ['chapter_id'], unique=False)
    op.create_index('ix_claim_novel_subject', 'claim', ['novel_id', 'subject_character_id', 'predicate'], unique=False)
    op.create_table('passage',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('novel_id', sa.Uuid(), nullable=False),
    sa.Column('chapter_id', sa.Uuid(), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('start', sa.Integer(), nullable=False),
    sa.Column('end', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('tsv', postgresql.TSVECTOR(), sa.Computed("to_tsvector('english', text)", persisted=True), nullable=False),
    sa.ForeignKeyConstraint(['chapter_id'], ['chapter.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['novel_id'], ['novel.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_passage_novel', 'passage', ['novel_id'], unique=False)
    op.create_index('ix_passage_tsv', 'passage', ['tsv'], unique=False, postgresql_using='gin')
    op.create_table('revision',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('chapter_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['chapter_id'], ['chapter.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('chapter_id', 'version')
    )
    op.create_table('evidence_span',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('claim_id', sa.Uuid(), nullable=False),
    sa.Column('chapter_id', sa.Uuid(), nullable=False),
    sa.Column('chapter_version', sa.Integer(), nullable=False),
    sa.Column('start', sa.Integer(), nullable=False),
    sa.Column('end', sa.Integer(), nullable=False),
    sa.Column('quote', sa.Text(), nullable=False),
    sa.CheckConstraint('start >= 0 AND "end" > start', name='span_bounds'),
    sa.ForeignKeyConstraint(['chapter_id'], ['chapter.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['claim_id'], ['claim.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_evidence_span_claim', 'evidence_span', ['claim_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_evidence_span_claim', table_name='evidence_span')
    op.drop_table('evidence_span')
    op.drop_table('revision')
    op.drop_index('ix_passage_tsv', table_name='passage', postgresql_using='gin')
    op.drop_index('ix_passage_novel', table_name='passage')
    op.drop_table('passage')
    op.drop_index('ix_claim_novel_subject', table_name='claim')
    op.drop_index('ix_claim_chapter', table_name='claim')
    op.drop_table('claim')
    op.drop_table('character')
    op.drop_table('chapter')
    op.drop_table('novel')
