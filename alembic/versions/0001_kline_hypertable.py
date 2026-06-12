"""kline table + Timescale hypertable

Revision ID: 0001
Revises:
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kline",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("tf", sa.String(), nullable=False),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(), nullable=False),
        sa.Column("high", sa.Numeric(), nullable=False),
        sa.Column("low", sa.Numeric(), nullable=False),
        sa.Column("close", sa.Numeric(), nullable=False),
        sa.Column("volume", sa.Numeric(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "tf", "ts"),
    )
    # Hypertable: chunk theo 7 ngày (extension đã bật ở db/init/01-extensions.sql).
    op.execute(
        "SELECT create_hypertable('kline', 'ts', "
        "chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE)"
    )


def downgrade() -> None:
    op.drop_table("kline")
