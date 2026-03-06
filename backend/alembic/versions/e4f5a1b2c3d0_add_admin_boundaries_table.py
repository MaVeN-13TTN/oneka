"""add admin_boundaries table

Revision ID: e4f5a1b2c3d0
Revises: c1624cd13ed2
Create Date: 2026-03-04

Adds the admin_boundaries table that stores Kenya Level-3 (Ward) boundary
polygons from UNOCHA HDX.  Centroid lat/lon are pre-computed and stored
denormalised for fast Tier-3 lookups by GeolocationService.

Load data with:
    python backend/scripts/load_ward_boundaries.py
"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f5a1b2c3d0"
down_revision: Union[str, None] = "c1624cd13ed2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_boundaries",
        sa.Column("boundary_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ward_code", sa.String(50), nullable=True, unique=True),
        sa.Column("constituency", sa.String(100), nullable=True),
        sa.Column("county", sa.String(100), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("centroid_lat", sa.DECIMAL(10, 7), nullable=True),
        sa.Column("centroid_lon", sa.DECIMAL(10, 7), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
            nullable=True,
        ),
    )

    # Indexes for frequent GeolocationService lookups
    op.create_index("ix_admin_boundaries_name", "admin_boundaries", ["name"])
    op.create_index("ix_admin_boundaries_county", "admin_boundaries", ["county"])
    op.create_index(
        "ix_admin_boundaries_constituency", "admin_boundaries", ["constituency"]
    )
    # Spatial index for PostGIS geometry queries
    op.create_index(
        "ix_admin_boundaries_geom",
        "admin_boundaries",
        ["geom"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_admin_boundaries_geom", table_name="admin_boundaries")
    op.drop_index(
        "ix_admin_boundaries_constituency", table_name="admin_boundaries"
    )
    op.drop_index("ix_admin_boundaries_county", table_name="admin_boundaries")
    op.drop_index("ix_admin_boundaries_name", table_name="admin_boundaries")
    op.drop_table("admin_boundaries")
