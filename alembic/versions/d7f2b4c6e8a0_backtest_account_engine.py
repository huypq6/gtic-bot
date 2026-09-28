"""backtest: account-simulation engine (P9c) — sizing/settings/stats columns + trade USDT/R

Revision ID: d7f2b4c6e8a0
Revises: c5e1a2b3d4f6
Create Date: 2026-09-27 02:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'd7f2b4c6e8a0'
down_revision: str | None = 'c5e1a2b3d4f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN = (('engine', sa.String()), ('sizing', postgresql.JSONB()), ('settings', postgresql.JSONB()),
       ('stats', postgresql.JSONB()), ('final_equity', sa.Numeric()))
TRADE = (('qty', sa.Numeric()), ('pnl', sa.Numeric()), ('fee', sa.Numeric()), ('r', sa.Numeric()),
         ('reason', sa.String()), ('mfe_r', sa.Numeric()), ('mae_r', sa.Numeric()))


def upgrade() -> None:
    for c, t in RUN:
        op.add_column('backtest_run', sa.Column(c, t))
    for c, t in TRADE:
        op.add_column('backtest_trade', sa.Column(c, t))
    op.execute("UPDATE backtest_run SET engine = 'VBT' WHERE engine IS NULL")


def downgrade() -> None:
    for c, _ in TRADE:
        op.drop_column('backtest_trade', c)
    for c, _ in RUN:
        op.drop_column('backtest_run', c)
