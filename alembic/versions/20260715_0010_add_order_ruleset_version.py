"""add non-null ruleset version to orders

Revision ID: 20260715_0010
Revises: 20260705_0009
Create Date: 2026-07-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260715_0010"
down_revision: Union[str, None] = "20260705_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_V2 = "FORTUNE_RULESET_2026_V2"


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(
            sa.Column(
                "ruleset_version",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text(f"'{_V2}'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("ruleset_version")
