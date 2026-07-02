"""add settlement payout posting fields

Revision ID: 20260702_0007
Revises: 20260701_0006
Create Date: 2026-07-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260702_0007"
down_revision: Union[str, None] = "20260701_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("settlement_records") as batch_op:
        batch_op.add_column(sa.Column("payout_posted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("payout_ledger_entry_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("payout_posted_amount", sa.Numeric(14, 2), nullable=True))
        batch_op.create_foreign_key(
            "fk_settlement_records_payout_ledger_entry",
            "account_ledger_entries",
            ["payout_ledger_entry_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_settlement_records_payout_posted_at",
            ["payout_posted_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_settlement_records_payout_ledger_entry_id",
            ["payout_ledger_entry_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("settlement_records") as batch_op:
        batch_op.drop_index("ix_settlement_records_payout_ledger_entry_id")
        batch_op.drop_index("ix_settlement_records_payout_posted_at")
        batch_op.drop_constraint("fk_settlement_records_payout_ledger_entry", type_="foreignkey")
        batch_op.drop_column("payout_posted_amount")
        batch_op.drop_column("payout_ledger_entry_id")
        batch_op.drop_column("payout_posted_at")
