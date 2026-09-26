"""position: exit_reason + init_sl (review lệnh: lý do thoát, R theo SL ban đầu)

Revision ID: a7c1e2d4f901
Revises: 3ca6a8351dba
Create Date: 2026-09-26 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a7c1e2d4f901'
down_revision: str | None = '3ca6a8351dba'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('position', sa.Column('exit_reason', sa.String(), nullable=True))
    op.add_column('position', sa.Column('init_sl', sa.Numeric(), nullable=True))
    # vị thế cũ: SL ban đầu ≈ SL hiện có (chưa ai sửa tay trong paper).
    op.execute("UPDATE position SET init_sl = sl WHERE init_sl IS NULL")


def downgrade() -> None:
    op.drop_column('position', 'init_sl')
    op.drop_column('position', 'exit_reason')
