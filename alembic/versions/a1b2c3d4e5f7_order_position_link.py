"""Link each fill to its trade: order.position_id + order.intent (OPEN = entry, CLOSE = exit).

Backfill is best-effort for existing rows: a FILLED order is matched to the position of the same
mode/symbol/bot whose entry (same side) or exit (opposite side) happened within 2 minutes at the
same price.

Revision ID: a1b2c3d4e5f7
Revises: e9a3c5d7f1b2
Create Date: 2026-10-05 10:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a1b2c3d4e5f7'
down_revision: str | None = 'e9a3c5d7f1b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MATCH = """
UPDATE "order" o SET position_id = m.pid, intent = '{intent}'
FROM (
  SELECT DISTINCT ON (o2.id) o2.id AS oid, p.id AS pid
  FROM "order" o2
  JOIN position p
    ON p.mode = o2.mode AND p.symbol = o2.symbol
   AND COALESCE(p.bot_ref, p.bot_id, -1) = COALESCE(o2.bot_id, -1)
   AND o2.side = CASE WHEN p.side = 'LONG' THEN '{long_side}' ELSE '{short_side}' END
   AND p.{ts} IS NOT NULL
   AND abs(extract(epoch FROM (o2.created_at - p.{ts}))) <= 120
   AND o2.price = p.{price}
  WHERE o2.status = 'FILLED' AND o2.position_id IS NULL
  ORDER BY o2.id, abs(extract(epoch FROM (o2.created_at - p.{ts})))
) m
WHERE o.id = m.oid
"""


def upgrade() -> None:
    op.add_column('order', sa.Column('position_id', sa.Integer()))
    op.add_column('order', sa.Column('intent', sa.String()))
    op.create_index('ix_order_position_id', 'order', ['position_id'])
    op.execute(_MATCH.format(intent='CLOSE', long_side='SELL', short_side='BUY',
                             ts='closed_at', price='exit_price'))
    op.execute(_MATCH.format(intent='OPEN', long_side='BUY', short_side='SELL',
                             ts='opened_at', price='entry_price'))


def downgrade() -> None:
    op.drop_index('ix_order_position_id', table_name='order')
    op.drop_column('order', 'intent')
    op.drop_column('order', 'position_id')
