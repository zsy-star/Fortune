"""create customer accounts and account ledger entries

Revision ID: 20260701_0006
Revises: 20260628_0005
Create Date: 2026-07-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260701_0006"
down_revision: Union[str, None] = "20260628_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_name", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_name", name="uq_customer_accounts_customer_name"),
    )
    op.create_index("ix_customer_accounts_customer_name", "customer_accounts", ["customer_name"], unique=True)
    op.create_index("ix_customer_accounts_status", "customer_accounts", ["status"], unique=False)
    op.create_index(
        "ix_customer_accounts_status_updated",
        "customer_accounts",
        ["status", "updated_at"],
        unique=False,
    )

    op.create_table(
        "account_ledger_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("customer_name", sa.String(length=128), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance_before", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(14, 2), nullable=False),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("settlement_record_id", sa.Integer(), nullable=True),
        sa.Column("adjustment_record_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("operator", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("audit_log_id", sa.Integer(), nullable=True),
        sa.Column("is_reversed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("reversed_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["adjustment_record_id"], ["adjustment_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["audit_log_id"], ["operation_logs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customer_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reversed_by_id"], ["account_ledger_entries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["settlement_record_id"], ["settlement_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reversed_by_id", name="uq_account_ledger_entries_reversed_by"),
    )
    op.create_index("ix_account_ledger_entries_audit_log_id", "account_ledger_entries", ["audit_log_id"])
    op.create_index("ix_account_ledger_entries_customer_id", "account_ledger_entries", ["customer_id"])
    op.create_index("ix_account_ledger_entries_customer_name", "account_ledger_entries", ["customer_name"])
    op.create_index("ix_account_ledger_entries_direction", "account_ledger_entries", ["direction"])
    op.create_index("ix_account_ledger_entries_entry_type", "account_ledger_entries", ["entry_type"])
    op.create_index(
        "ix_account_ledger_customer_created",
        "account_ledger_entries",
        ["customer_id", "created_at"],
    )
    op.create_index(
        "ix_account_ledger_entry_type_created",
        "account_ledger_entries",
        ["entry_type", "created_at"],
    )
    op.create_index("ix_account_ledger_source", "account_ledger_entries", ["source_type", "source_id"])


def downgrade() -> None:
    op.drop_index("ix_account_ledger_source", table_name="account_ledger_entries")
    op.drop_index("ix_account_ledger_entry_type_created", table_name="account_ledger_entries")
    op.drop_index("ix_account_ledger_customer_created", table_name="account_ledger_entries")
    op.drop_index("ix_account_ledger_entries_entry_type", table_name="account_ledger_entries")
    op.drop_index("ix_account_ledger_entries_direction", table_name="account_ledger_entries")
    op.drop_index("ix_account_ledger_entries_customer_name", table_name="account_ledger_entries")
    op.drop_index("ix_account_ledger_entries_customer_id", table_name="account_ledger_entries")
    op.drop_index("ix_account_ledger_entries_audit_log_id", table_name="account_ledger_entries")
    op.drop_table("account_ledger_entries")
    op.drop_index("ix_customer_accounts_status_updated", table_name="customer_accounts")
    op.drop_index("ix_customer_accounts_status", table_name="customer_accounts")
    op.drop_index("ix_customer_accounts_customer_name", table_name="customer_accounts")
    op.drop_table("customer_accounts")
