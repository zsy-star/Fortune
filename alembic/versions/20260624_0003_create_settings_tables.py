"""create settings center tables

Revision ID: 20260624_0003
Revises: 20260624_0002
Create Date: 2026-06-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260624_0003"
down_revision: Union[str, None] = "20260624_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "odds_rebate_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "odds_rebate_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("bet_type", sa.String(length=128), nullable=False),
        sa.Column("odds", sa.Numeric(12, 4), nullable=False),
        sa.Column("rebate", sa.Numeric(6, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["odds_rebate_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "bet_type", name="uq_odds_rebate_items_plan_bet_type"),
    )
    op.create_index("ix_odds_rebate_items_plan_id", "odds_rebate_items", ["plan_id"], unique=False)
    op.create_table(
        "declarer_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["odds_rebate_plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_declarer_settings_plan_id", "declarer_settings", ["plan_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_declarer_settings_plan_id", table_name="declarer_settings")
    op.drop_table("declarer_settings")
    op.drop_index("ix_odds_rebate_items_plan_id", table_name="odds_rebate_items")
    op.drop_table("odds_rebate_items")
    op.drop_table("odds_rebate_plans")
