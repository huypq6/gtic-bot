"""account + account_txn (ledger) + bot.account_id/sizing + position.account_id/fee/margin/risk

Creates a default paper account with 1,000 USDT; assigns every PAPER bot to it, money management
defaults to 1% risk per trade.

Revision ID: c5e1a2b3d4f6
Revises: b3d9f0a1c2e4
Create Date: 2026-09-27 00:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'c5e1a2b3d4f6'
down_revision: str | None = 'b3d9f0a1c2e4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'account',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False, server_default='PAPER'),
        sa.Column('currency', sa.String(), nullable=False, server_default='USDT'),
        sa.Column('balance', sa.Numeric(), nullable=False, server_default='0'),
        sa.Column('peak_equity', sa.Numeric(), nullable=False, server_default='0'),
        sa.Column('leverage', sa.Numeric(), nullable=False, server_default='1'),
        sa.Column('taker_fee', sa.Numeric(), nullable=False, server_default='0.0005'),
        sa.Column('maker_fee', sa.Numeric(), nullable=False, server_default='0.0002'),
        sa.Column('slippage_bps', sa.Numeric(), nullable=False, server_default='2'),
        sa.Column('max_risk_pct', sa.Numeric()),
        sa.Column('max_open_risk_pct', sa.Numeric()),
        sa.Column('max_positions', sa.Integer()),
        sa.Column('daily_loss_pct', sa.Numeric()),
        sa.Column('max_dd_pct', sa.Numeric()),
        sa.Column('status', sa.String(), nullable=False, server_default='ACTIVE'),
        sa.Column('halted_reason', sa.String()),
        sa.Column('halted_until', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.CheckConstraint("status IN ('ACTIVE','HALTED')", name='ck_account_status'),
        sa.CheckConstraint("mode IN ('PAPER','TESTNET','LIVE')", name='ck_account_mode'),
    )
    op.create_table(
        'account_txn',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('account_id', sa.Integer(),
                  sa.ForeignKey('account.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('amount', sa.Numeric(), nullable=False),
        sa.Column('balance_after', sa.Numeric(), nullable=False),
        sa.Column('position_id', sa.Integer()),
        sa.Column('bot_id', sa.Integer()),
        sa.Column('symbol', sa.String()),
        sa.Column('note', sa.String()),
        sa.CheckConstraint(
            "type IN ('DEPOSIT','WITHDRAW','REALIZED_PNL','FEE','ADJUST')", name='ck_txn_type'
        ),
    )
    op.create_index('ix_account_txn_account_ts', 'account_txn', ['account_id', 'ts'])
    op.add_column('bot', sa.Column('account_id', sa.Integer(), sa.ForeignKey('account.id')))
    op.add_column('bot', sa.Column('sizing', postgresql.JSONB()))
    for c, t in (('account_id', sa.Integer()), ('fee', sa.Numeric()),
                 ('margin', sa.Numeric()), ('risk_amount', sa.Numeric())):
        op.add_column('position', sa.Column(c, t))

    op.execute("""
        WITH a AS (
            INSERT INTO account (name, balance, peak_equity, max_risk_pct, max_open_risk_pct,
                                 daily_loss_pct, max_dd_pct)
            VALUES ('Main paper', 1000, 1000, 2, 6, 3, 15) RETURNING id
        ), t AS (
            INSERT INTO account_txn (account_id, type, amount, balance_after, note)
            SELECT id, 'DEPOSIT', 1000, 1000, 'Initial capital' FROM a
        )
        UPDATE bot SET account_id = (SELECT id FROM a),
                       sizing = '{"method": "risk_pct", "value": 1}'::jsonb
        WHERE mode = 'PAPER'
    """)


def downgrade() -> None:
    for c in ('risk_amount', 'margin', 'fee', 'account_id'):
        op.drop_column('position', c)
    op.drop_column('bot', 'sizing')
    op.drop_column('bot', 'account_id')
    op.drop_index('ix_account_txn_account_ts', table_name='account_txn')
    op.drop_table('account_txn')
    op.drop_table('account')
