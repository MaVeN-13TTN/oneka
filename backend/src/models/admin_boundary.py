"""
SQLAlchemy model for Kenya administrative boundaries.

Stores UNOCHA Kenya Level 3 (Ward) boundaries used by GeolocationService
as the Tier 3 (lowest-confidence) GPS fallback — ward centroid coordinates
are used when neither eGP GPS (Tier 1) nor KMHFL fuzzy match (Tier 2)
can resolve a project location.

Populated by: backend/scripts/load_ward_boundaries.py
Used by:      backend/src/services/geolocation_service.py (Tier 3 fallback)
"""

from geoalchemy2 import Geometry
from sqlalchemy import Column, DECIMAL, Integer, String

from src.database import Base


class AdminBoundary(Base):
    """Kenya administrative boundary — ward-level (L3)."""

    __tablename__ = "admin_boundaries"

    boundary_id = Column(Integer, primary_key=True, autoincrement=True)

    # Boundary name hierarchy
    name = Column(String, nullable=False, index=True)           # ward name
    ward_code = Column(String(50), nullable=True, unique=True)  # IEBC ward code
    constituency = Column(String(100), nullable=True, index=True)
    county = Column(String(100), nullable=True, index=True)

    # Admin level: 1=country, 2=county, 3=ward
    level = Column(Integer, nullable=False, default=3)

    # Pre-computed centroid (calculated from geom at load time)
    centroid_lat = Column(DECIMAL(10, 7), nullable=True)
    centroid_lon = Column(DECIMAL(10, 7), nullable=True)

    # PostGIS geometry (MULTIPOLYGON — some wards are non-contiguous)
    geom = Column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AdminBoundary id={self.boundary_id} "
            f"ward={self.name!r} county={self.county!r}>"
        )
