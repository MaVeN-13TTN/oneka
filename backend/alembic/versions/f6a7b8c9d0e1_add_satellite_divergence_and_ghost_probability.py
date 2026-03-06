"""add satellite divergence columns and ghost probability

Revision ID: f6a7b8c9d0e1
Revises: e4f5a1b2c3d0
Create Date: 2026-03-06 00:00:00.000000

Adds:
- satellite_analyses.ndvi_slope       DECIMAL(8,4)  — NDVI change per month (linear regression)
- satellite_analyses.sar_backscatter_delta  DECIMAL(8,4)  — SAR VV Δ vs baseline (dB)
- projects.ghost_probability          NUMERIC(5,4)  — ML ghost probability (Phase 4)
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e4f5a1b2c3d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- satellite_analyses ---
    op.add_column(
        "satellite_analyses",
        sa.Column(
            "ndvi_slope",
            sa.DECIMAL(8, 4),
            nullable=True,
            comment="Linear regression slope of ndvi_mean over time (NDVI/month); "
                    "negative = land clearing / construction activity",
        ),
    )
    op.add_column(
        "satellite_analyses",
        sa.Column(
            "sar_backscatter_delta",
            sa.DECIMAL(8, 4),
            nullable=True,
            comment="SAR VV backscatter change vs baseline scene (dB); "
                    "positive = new structures appearing",
        ),
    )

    # --- projects ---
    op.add_column(
        "projects",
        sa.Column(
            "ghost_probability",
            sa.Numeric(5, 4),
            nullable=True,
            comment="ML-predicted ghost project probability 0.0000–1.0000; "
                    "populated by Phase 4 risk scoring pipeline",
        ),
    )


def downgrade() -> None:
    op.drop_column("satellite_analyses", "ndvi_slope")
    op.drop_column("satellite_analyses", "sar_backscatter_delta")
    op.drop_column("projects", "ghost_probability")
