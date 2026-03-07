"""add investigation_id FK to procurement and financial records

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-08 00:00:00.000000

Adds a nullable investigation_id FK column to:
  - procurement_records  → links to investigations.investigation_id
  - financial_records    → links to investigations.investigation_id

These columns are NULL for all records created by bulk/scheduled scrapes.
They are populated by investigate_project_task to allow the report endpoint
to fetch only the evidence gathered for a specific investigation.
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── procurement_records ──────────────────────────────────────────────────
    op.add_column(
        "procurement_records",
        sa.Column(
            "investigation_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey(
                "investigations.investigation_id",
                ondelete="SET NULL",
                name="fk_procurement_investigation_id",
            ),
            nullable=True,
            comment="Investigation that created this record (NULL for bulk scrapes)",
        ),
    )
    op.create_index(
        "idx_procurement_investigation_id",
        "procurement_records",
        ["investigation_id"],
    )

    # ── financial_records ────────────────────────────────────────────────────
    op.add_column(
        "financial_records",
        sa.Column(
            "investigation_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey(
                "investigations.investigation_id",
                ondelete="SET NULL",
                name="fk_financial_investigation_id",
            ),
            nullable=True,
            comment="Investigation that created this record (NULL for bulk ingestion)",
        ),
    )
    op.create_index(
        "idx_financial_investigation_id",
        "financial_records",
        ["investigation_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_financial_investigation_id", table_name="financial_records")
    op.drop_column("financial_records", "investigation_id")
    op.drop_index(
        "idx_procurement_investigation_id", table_name="procurement_records"
    )
    op.drop_column("procurement_records", "investigation_id")
