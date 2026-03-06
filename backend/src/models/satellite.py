"""
Satellite Analysis model - Store satellite metrics and change detection results.
"""

from sqlalchemy import Column, String, Integer, DECIMAL, Date, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class SatelliteAnalysis(Base, TimestampMixin):
    """
    Satellite analysis results from Sentinel-1 (SAR) and Sentinel-2 (optical).

    Stores NDVI, SAR backscatter, and other indices for change detection
    and ML-based ghost project prediction.
    """

    __tablename__ = "satellite_analyses"

    # Primary Key
    analysis_id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Key to Project
    project_uuid = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to parent project",
    )

    # Satellite Information
    sensor = Column(
        String(20),
        nullable=False,
        comment="Satellite sensor: 'Sentinel-1', 'Sentinel-2', 'SkySat'",
    )

    acquisition_date = Column(
        Date, nullable=False, index=True, comment="Date satellite image was captured"
    )

    scene_id = Column(
        String, nullable=True, comment="Original satellite scene identifier"
    )

    cloud_cover_percentage = Column(
        Integer,
        nullable=True,
        comment="Cloud cover percentage (0-100) for optical imagery",
    )

    # Analysis Type
    analysis_type = Column(
        String(50),
        nullable=False,
        comment="Analysis: 'NDVI_change', 'SAR_backscatter', 'RGB_inspection', 'NDWI_water'",
    )

    # Metrics
    baseline_value = Column(
        DECIMAL(10, 4),
        nullable=True,
        comment="Baseline metric value (pre-construction)",
    )

    current_value = Column(
        DECIMAL(10, 4), nullable=True, comment="Current metric value"
    )

    change_magnitude = Column(
        DECIMAL(10, 4), nullable=True, comment="Change in metric (current - baseline)"
    )

    change_detected = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether significant change was detected",
    )

    # NDVI-specific metrics
    ndvi_mean = Column(
        DECIMAL(6, 4), nullable=True, comment="Mean NDVI value for project site"
    )

    ndvi_std = Column(
        DECIMAL(6, 4), nullable=True, comment="Standard deviation of NDVI"
    )

    ndvi_min = Column(DECIMAL(6, 4), nullable=True, comment="Minimum NDVI in area")

    ndvi_max = Column(DECIMAL(6, 4), nullable=True, comment="Maximum NDVI in area")

    # SAR-specific metrics
    sar_vv_mean = Column(
        DECIMAL(8, 4), nullable=True, comment="Mean VV backscatter (dB)"
    )

    sar_vh_mean = Column(
        DECIMAL(8, 4), nullable=True, comment="Mean VH backscatter (dB)"
    )

    # Derived temporal metrics (Phase 3)
    ndvi_slope = Column(
        DECIMAL(8, 4),
        nullable=True,
        comment="Linear regression slope of ndvi_mean over time (NDVI/month); negative = land clearing",
    )

    sar_backscatter_delta = Column(
        DECIMAL(8, 4),
        nullable=True,
        comment="SAR VV backscatter delta vs baseline (dB); positive = new structures appearing",
    )

    # Interpretation
    interpretation = Column(
        Text, nullable=True, comment="Human-readable interpretation of analysis"
    )

    construction_phase = Column(
        String(50),
        nullable=True,
        comment="Detected phase: 'pre-construction', 'land_clearing', 'foundation', 'superstructure', 'completion'",
    )

    # Data Storage
    image_url = Column(String, nullable=True, comment="URL to processed GeoTIFF in S3")

    thumbnail_url = Column(
        String, nullable=True, comment="URL to thumbnail/preview image"
    )

    tile_url_template = Column(
        String, nullable=True, comment="XYZ tile URL template for web maps"
    )

    # Processing Metadata
    processing_algorithm = Column(
        String(50), nullable=True, comment="Algorithm used: 'satpy', 'pyrosar', 'snap'"
    )

    processing_date = Column(Date, nullable=True, comment="Date analysis was performed")

    # Relationship
    project = relationship("Project", back_populates="satellite_analyses")

    def __repr__(self):
        return f"<SatelliteAnalysis(sensor={self.sensor}, date={self.acquisition_date}, type={self.analysis_type})>"
