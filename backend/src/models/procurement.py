"""
Procurement Record model - Tender data from PPIP and other sources.
"""

from sqlalchemy import Column, String, Integer, DECIMAL, Date, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class ProcurementRecord(Base, TimestampMixin):
    """
    Procurement records from tendering systems (PPIP, eGP, agency portals).

    Stores tender awards, contract details, and contractor information.
    """

    __tablename__ = "procurement_records"

    # Primary Key
    procurement_id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Key to Project
    project_uuid = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Reference to parent project (NULL until entity resolution in Sprint 3)",
    )

    # Source Information
    source_system = Column(
        String(50),
        nullable=False,
        comment="Source system: 'PPIP', 'eGP', 'KeNHA', 'KURA', etc.",
    )

    # Tender Details
    tender_number = Column(
        String,
        unique=True,
        nullable=False,
        index=True,
        comment="Unique tender identifier from source system",
    )

    tender_title = Column(
        String, nullable=True, comment="Official tender title/description"
    )

    procuring_entity = Column(
        String,
        nullable=True,
        index=True,
        comment="Ministry/department/agency issuing tender",
    )

    # Contract Information
    contract_sum_kes = Column(
        DECIMAL(15, 2),
        nullable=True,
        comment="Contract award amount in Kenya Shillings",
    )

    award_date = Column(
        Date, nullable=True, index=True, comment="Date contract was awarded"
    )

    expected_completion_date = Column(
        Date, nullable=True, comment="Expected project completion date"
    )

    contract_duration_months = Column(
        Integer, nullable=True, comment="Contract duration in months"
    )

    # Contractor Details
    contractor_name = Column(
        String, nullable=True, index=True, comment="Name of awarded contractor/company"
    )

    contractor_pin = Column(
        String(20),
        nullable=True,
        comment="Contractor PIN (Personal Identification Number)",
    )

    contractor_nca_license = Column(
        String(50),
        nullable=True,
        comment="NCA (National Construction Authority) license number",
    )

    # Document Storage
    document_url = Column(
        String, nullable=True, comment="URL to original tender document (PDF)"
    )

    document_s3_key = Column(
        String, nullable=True, comment="S3 object key if document stored in cloud"
    )

    raw_ocr_text = Column(
        Text, nullable=True, comment="Full extracted text from PDF for search"
    )

    # Data Quality
    data_quality = Column(
        Integer, nullable=True, comment="OCR/extraction quality score 0-100"
    )

    extraction_method = Column(
        String(50),
        nullable=True,
        comment="Method used: 'api', 'scraping', 'ocr', 'manual'",
    )

    # Relationship
    project = relationship("Project", back_populates="procurement_records")

    def __repr__(self):
        return f"<ProcurementRecord(tender={self.tender_number}, contractor='{self.contractor_name}')>"
