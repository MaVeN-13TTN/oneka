"""add_egp_gps_fields_to_procurement_records

Revision ID: c1624cd13ed2
Revises: bcf9c05b9fb7
Create Date: 2026-03-04 16:17:44.543339

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1624cd13ed2'
down_revision: Union[str, None] = 'bcf9c05b9fb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "procurement_records",
        sa.Column("egp_tender_id", sa.String(), nullable=True,
                  comment="Internal eGP tender ID from API response"),
    )
    op.add_column(
        "procurement_records",
        sa.Column("delivery_latitude", sa.DECIMAL(10, 7), nullable=True,
                  comment="Delivery location latitude from eGP (Tier 1 GPS)"),
    )
    op.add_column(
        "procurement_records",
        sa.Column("delivery_longitude", sa.DECIMAL(10, 7), nullable=True,
                  comment="Delivery location longitude from eGP (Tier 1 GPS)"),
    )
    op.add_column(
        "procurement_records",
        sa.Column("gps_source", sa.String(50), nullable=True,
                  comment="GPS origin: EGP_MANUAL_PIN | EGP_AUTO_GEOCODED | KMHFL_MATCHED | WARD_CENTROID"),
    )
    op.add_column(
        "procurement_records",
        sa.Column("gps_quality_score", sa.Integer(), nullable=True,
                  comment="GPS quality 0-100: manual pin=90, auto=70, fuzzy match=60-80, ward=20"),
    )


def downgrade() -> None:
    op.drop_column("procurement_records", "gps_quality_score")
    op.drop_column("procurement_records", "gps_source")
    op.drop_column("procurement_records", "delivery_longitude")
    op.drop_column("procurement_records", "delivery_latitude")
    op.drop_column("procurement_records", "egp_tender_id")
