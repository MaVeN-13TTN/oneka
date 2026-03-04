"""
SQLAlchemy Core table definitions for data-layer scrapers.

These are lightweight table mirrors used only for INSERT/UPSERT operations.
They intentionally omit relationships and constraints that live in the
backend ORM models, keeping the data venv dependency-free from the
backend's pydantic-settings / FastAPI stack.

Column names and types must stay in sync with:
    backend/alembic/versions/  (the canonical schema source)
"""

from sqlalchemy import (
    Column,
    Date,
    DECIMAL,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData()

# ── procurement_records ───────────────────────────────────────────────────────
procurement_records = Table(
    "procurement_records",
    metadata,
    Column("procurement_id", Integer, primary_key=True, autoincrement=True),
    Column("project_uuid", UUID(as_uuid=True), nullable=True),
    Column("source_system", String(50), nullable=False),
    Column("tender_number", String, unique=True, nullable=False),
    Column("tender_title", String, nullable=True),
    Column("procuring_entity", String, nullable=True),
    Column("contract_sum_kes", DECIMAL(15, 2), nullable=True),
    Column("award_date", Date, nullable=True),
    Column("expected_completion_date", Date, nullable=True),
    Column("contract_duration_months", Integer, nullable=True),
    Column("contractor_name", String, nullable=True),
    Column("contractor_pin", String(20), nullable=True),
    Column("contractor_nca_license", String(50), nullable=True),
    Column("document_url", String, nullable=True),
    Column("document_s3_key", String, nullable=True),
    Column("raw_ocr_text", Text, nullable=True),
    Column("data_quality", Integer, nullable=True),
    Column("extraction_method", String(50), nullable=True),
    # EGP GPS fields (migration c1624cd13ed2)
    Column("egp_tender_id", String, nullable=True),
    Column("delivery_latitude", DECIMAL(10, 7), nullable=True),
    Column("delivery_longitude", DECIMAL(10, 7), nullable=True),
    Column("gps_source", String(50), nullable=True),
    Column("gps_quality_score", Integer, nullable=True),
)

# ── geolocation_records ───────────────────────────────────────────────────────
geolocation_records = Table(
    "geolocation_records",
    metadata,
    Column("geolocation_id", Integer, primary_key=True, autoincrement=True),
    Column("project_uuid", UUID(as_uuid=True), nullable=True),
    Column("source_system", String(50), nullable=True),
    Column("facility_code", String(50), nullable=True),
    Column("facility_name", String, nullable=True),
    Column("latitude", DECIMAL(10, 7), nullable=False),
    Column("longitude", DECIMAL(10, 7), nullable=False),
    Column("match_confidence", Integer, nullable=True),
    Column("match_method", String(50), nullable=True),
    Column("match_score", Integer, nullable=True),
    Column("verified", Integer, nullable=True, default=0),
    Column("address", String, nullable=True),
)
