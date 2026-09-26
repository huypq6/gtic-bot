"""position: snapshot source/bot_ref/strategy/tf/params lúc mở lệnh

Xóa bot → bot_id của position bị NULL → review mất chiến lược, hiện nhầm MANUAL.
Snapshot giữ nguyên thông tin. Backfill: còn bot → chép từ bot; mồ côi → khớp audit_log
(BOT BUY/SELL cùng symbol, lệch ≤ 5s so với opened_at) để lấy lại bot gốc.

Revision ID: b3d9f0a1c2e4
Revises: a7c1e2d4f901
Create Date: 2026-09-26 23:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'b3d9f0a1c2e4'
down_revision: str | None = 'a7c1e2d4f901'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('position', sa.Column('source', sa.String(), nullable=True))
    op.add_column('position', sa.Column('bot_ref', sa.Integer(), nullable=True))
    op.add_column('position', sa.Column('strategy', sa.String(), nullable=True))
    op.add_column('position', sa.Column('tf', sa.String(), nullable=True))
    op.add_column('position', sa.Column('params', postgresql.JSONB(), nullable=True))
    op.execute("""
        UPDATE position p SET source = 'BOT', bot_ref = b.id,
               strategy = s.name || ' v' || s.version, tf = b.tf, params = b.params
        FROM bot b JOIN strategy s ON s.id = b.strategy_id
        WHERE p.bot_id = b.id
    """)
    op.execute("""
        UPDATE position p SET source = 'BOT', bot_ref = a.bot_id
        FROM audit_log a
        WHERE p.bot_id IS NULL AND a.source = 'BOT' AND a.bot_id IS NOT NULL
          AND a.action IN ('BUY', 'SELL') AND a.symbol = p.symbol AND a.mode = p.mode
          AND abs(extract(epoch FROM a.ts - p.opened_at)) <= 5
    """)
    op.execute("UPDATE position SET source = 'MANUAL' WHERE source IS NULL")


def downgrade() -> None:
    for c in ('params', 'tf', 'strategy', 'bot_ref', 'source'):
        op.drop_column('position', c)
