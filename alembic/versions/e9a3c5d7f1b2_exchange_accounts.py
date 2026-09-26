"""P9b: tài khoản sàn (TESTNET/LIVE Futures) — cache số dư sàn, con trỏ sổ cái income,
ext_id chống nhập trùng, loại FUNDING, id SL/TP đặt trên sàn của vị thế.

Revision ID: e9a3c5d7f1b2
Revises: d7f2b4c6e8a0
Create Date: 2026-09-27 10:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'e9a3c5d7f1b2'
down_revision: str | None = 'd7f2b4c6e8a0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACC = (('exch_equity', sa.Numeric()), ('exch_unrealized', sa.Numeric()),
       ('exch_margin', sa.Numeric()), ('exch_available', sa.Numeric()),
       ('income_cursor', sa.BigInteger()), ('last_sync_at', sa.DateTime(timezone=True)),
       ('sync_error', sa.String()))


def upgrade() -> None:
    op.add_column('account', sa.Column('market', sa.String(), nullable=False,
                                       server_default='FUTURES'))
    for c, t in ACC:
        op.add_column('account', sa.Column(c, t))
    op.add_column('account_txn', sa.Column('ext_id', sa.String()))
    op.create_unique_constraint('uq_txn_ext', 'account_txn', ['account_id', 'ext_id'])
    op.drop_constraint('ck_txn_type', 'account_txn', type_='check')
    op.create_check_constraint(
        'ck_txn_type', 'account_txn',
        "type IN ('DEPOSIT','WITHDRAW','REALIZED_PNL','FEE','FUNDING','ADJUST')",
    )
    op.add_column('position', sa.Column('ext_protect', postgresql.JSONB()))


def downgrade() -> None:
    op.drop_column('position', 'ext_protect')
    op.drop_constraint('ck_txn_type', 'account_txn', type_='check')
    op.create_check_constraint(
        'ck_txn_type', 'account_txn',
        "type IN ('DEPOSIT','WITHDRAW','REALIZED_PNL','FEE','ADJUST')",
    )
    op.drop_constraint('uq_txn_ext', 'account_txn', type_='unique')
    op.drop_column('account_txn', 'ext_id')
    for c, _ in ACC:
        op.drop_column('account', c)
    op.drop_column('account', 'market')
