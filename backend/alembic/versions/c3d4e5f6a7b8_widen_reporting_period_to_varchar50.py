"""widen reporting_period to varchar(50)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-11 14:30:00.000000

COB BIRR reports use period labels like 'First Nine Months FY 2019/20'
(30 chars) which overflow the original VARCHAR(20) limit.
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "financial_records",
        "reporting_period",
        type_=sa.String(50),
        existing_type=sa.String(20),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "financial_records",
        "reporting_period",
        type_=sa.String(20),
        existing_type=sa.String(50),
        existing_nullable=True,
    )
