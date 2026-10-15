"""review decision value

Also: claim fingerprints now include the chapter id, so decisions recorded before this
revision no longer match and claims return to "proposed" on their next rebuild.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-15 03:14:09.240011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("review_decision", sa.Column("value", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("review_decision", "value")
