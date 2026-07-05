"""add zodiac year to orders

Revision ID: 20260705_0009
Revises: 20260702_0008
Create Date: 2026-07-05

Existing orders are backfilled to 2026, the current project zodiac baseline
where 01 belongs to 马. The column remains nullable for compatibility with
older databases and external imports; runtime code falls back to the default
zodiac year when the value is missing.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260705_0009"
down_revision: Union[str, None] = "20260702_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("zodiac_year", sa.Integer(), nullable=True))

    op.execute("UPDATE orders SET zodiac_year = 2026 WHERE zodiac_year IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("zodiac_year")

