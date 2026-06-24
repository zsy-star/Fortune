"""create settlement records table

Revision ID: 20260624_0002
Revises: 20260612_0001
Create Date: 2026-06-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260624_0002"
down_revision: Union[str, None] = "20260612_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "settlement_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("draw_id", sa.Integer(), nullable=False),
        sa.Column("operation_log_id", sa.Integer(), nullable=True),
        sa.Column("region", sa.String(length=16), nullable=False),
        sa.Column("issue_number", sa.String(length=32), nullable=False),
        sa.Column("settled_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.Column("miss_count", sa.Integer(), nullable=False),
        sa.Column("unsupported_count", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["draw_id"], ["lottery_draws.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["operation_log_id"], ["operation_logs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_settlement_records_order_id"),
    )
    op.create_index("ix_settlement_records_draw_id", "settlement_records", ["draw_id"], unique=False)
    op.create_index("ix_settlement_records_issue", "settlement_records", ["region", "issue_number"], unique=False)
    op.create_index("ix_settlement_records_issue_number", "settlement_records", ["issue_number"], unique=False)
    op.create_index("ix_settlement_records_operation_log_id", "settlement_records", ["operation_log_id"], unique=False)
    op.create_index("ix_settlement_records_order_id", "settlement_records", ["order_id"], unique=False)
    op.create_index("ix_settlement_records_region", "settlement_records", ["region"], unique=False)
    op.create_index(
        "ix_settlement_records_region_settled_at",
        "settlement_records",
        ["region", "settled_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_settlement_records_region_settled_at", table_name="settlement_records")
    op.drop_index("ix_settlement_records_region", table_name="settlement_records")
    op.drop_index("ix_settlement_records_order_id", table_name="settlement_records")
    op.drop_index("ix_settlement_records_operation_log_id", table_name="settlement_records")
    op.drop_index("ix_settlement_records_issue_number", table_name="settlement_records")
    op.drop_index("ix_settlement_records_issue", table_name="settlement_records")
    op.drop_index("ix_settlement_records_draw_id", table_name="settlement_records")
    op.drop_table("settlement_records")
