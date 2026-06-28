"""create adjustment records table

Revision ID: 20260628_0005
Revises: 20260626_0004
Create Date: 2026-06-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260628_0005"
down_revision: Union[str, None] = "20260626_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "adjustment_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("adjustment_type", sa.String(length=16), nullable=False),
        sa.Column("region", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("source_filter", sa.JSON(), nullable=False),
        sa.Column("original_total", sa.String(length=32), nullable=False),
        sa.Column("adjustment_total", sa.String(length=32), nullable=False),
        sa.Column("after_total", sa.String(length=32), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("positive_count", sa.Integer(), nullable=False),
        sa.Column("negative_count", sa.Integer(), nullable=False),
        sa.Column("record_snapshot", sa.JSON(), nullable=False),
        sa.Column("summary_snapshot", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_adjustment_records_adjustment_type", "adjustment_records", ["adjustment_type"], unique=False)
    op.create_index("ix_adjustment_records_region", "adjustment_records", ["region"], unique=False)
    op.create_index(
        "ix_adjustment_records_region_created",
        "adjustment_records",
        ["region", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_adjustment_records_type_created",
        "adjustment_records",
        ["adjustment_type", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_adjustment_records_type_created", table_name="adjustment_records")
    op.drop_index("ix_adjustment_records_region_created", table_name="adjustment_records")
    op.drop_index("ix_adjustment_records_region", table_name="adjustment_records")
    op.drop_index("ix_adjustment_records_adjustment_type", table_name="adjustment_records")
    op.drop_table("adjustment_records")
