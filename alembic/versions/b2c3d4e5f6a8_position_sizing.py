"""position.sizing: account sizing snapshot at entry (requested vs actual risk, reduction notes).

Backfill from audit_log: the bot's opening order (BUY/SELL with sizing info) logged within
10 minutes before the position opened (audit is written BEFORE the executor acts).

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-10-05 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'b2c3d4e5f6a8'
down_revision: str | None = 'a1b2c3d4e5f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('position', sa.Column('sizing', postgresql.JSONB()))
    op.execute("""
UPDATE position p SET sizing = m.s
FROM (
  SELECT DISTINCT ON (p2.id) p2.id AS pid,
    (a.detail - 'size' - 'type') || CASE
      WHEN a.detail->'sizing'->>'method' = 'risk_pct' THEN jsonb_build_object('risk_target',
        round(((a.detail->>'equity')::numeric * (a.detail->'sizing'->>'value')::numeric / 100), 4))
      WHEN a.detail->'sizing'->>'method' = 'risk_usdt' THEN jsonb_build_object('risk_target',
        (a.detail->'sizing'->>'value')::numeric)
      ELSE '{}'::jsonb END AS s
  FROM position p2
  JOIN audit_log a
    ON a.bot_id = COALESCE(p2.bot_ref, p2.bot_id) AND a.symbol = p2.symbol AND a.mode = p2.mode
   AND a.action IN ('BUY', 'SELL') AND a.detail ? 'sizing'
   AND a.ts BETWEEN p2.opened_at - interval '10 minutes' AND p2.opened_at + interval '5 seconds'
  WHERE p2.sizing IS NULL
  ORDER BY p2.id, a.ts DESC
) m
WHERE p.id = m.pid
""")


def downgrade() -> None:
    op.drop_column('position', 'sizing')
