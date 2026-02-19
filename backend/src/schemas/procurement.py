"""
Pydantic schemas for procurement records (tenders).
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


class ProcurementRecordBase(BaseModel):
    """Base schema for procurement records with common fields"""

    source_system: str = Field(
        ...,
        description="Source system: 'PPIP', 'eGP', 'KeNHA', 'KURA', etc.",
        max_length=50,
    )
    tender_number: str = Field(
        ..., description="Unique tender identifier from source system"
    )
    tender_title: Optional[str] = Field(
        default=None, description="Official tender title/description"
    )
    procuring_entity: Optional[str] = Field(
        default=None, description="Ministry/department/agency issuing tender"
    )
    contract_sum_kes: Optional[Decimal] = Field(
        default=None, description="Contract award amount in Kenya Shillings", ge=0
    )
    award_date: Optional[date] = Field(
        default=None, description="Date contract was awarded"
    )
    expected_completion_date: Optional[date] = Field(
        default=None, description="Expected project completion date"
    )
    contract_duration_months: Optional[int] = Field(
        default=None, description="Contract duration in months", ge=0
    )
    contractor_name: Optional[str] = Field(
        default=None, description="Name of awarded contractor/company"
    )
    contractor_pin: Optional[str] = Field(
        default=None,
        description="Contractor PIN (Personal Identification Number)",
        max_length=20,
    )
    contractor_nca_license: Optional[str] = Field(
        default=None,
        description="NCA (National Construction Authority) license number",
        max_length=50,
    )
    document_url: Optional[str] = Field(
        default=None, description="URL to original tender document (PDF)"
    )
    document_s3_key: Optional[str] = Field(
        default=None, description="S3 object key if document stored in cloud"
    )
    raw_ocr_text: Optional[str] = Field(
        default=None, description="Full extracted text from PDF for search"
    )
    data_quality: Optional[int] = Field(
        default=None, description="OCR/extraction quality score 0-100", ge=0, le=100
    )
    extraction_method: Optional[str] = Field(
        default=None,
        description="Method used: 'api', 'scraping', 'ocr', 'manual'",
        max_length=50,
    )

    @field_validator("source_system")
    @classmethod
    def validate_source_system(cls, v: str) -> str:
        """Validate source system is from known sources"""
        allowed_sources = {"PPIP", "eGP", "KeNHA", "KURA", "Manual", "API"}
        if v not in allowed_sources:
            # Allow other sources but normalize
            return v.upper()
        return v


class ProcurementRecordCreate(ProcurementRecordBase):
    """Schema for creating a new procurement record"""

    project_uuid: Optional[UUID] = Field(
        default=None,
        description="Reference to parent project (optional for initial scraping)",
    )


class ProcurementRecordUpdate(BaseModel):
    """Schema for updating a procurement record (all fields optional)"""

    project_uuid: Optional[UUID] = None
    source_system: Optional[str] = None
    tender_number: Optional[str] = None
    tender_title: Optional[str] = None
    procuring_entity: Optional[str] = None
    contract_sum_kes: Optional[Decimal] = None
    award_date: Optional[date] = None
    expected_completion_date: Optional[date] = None
    contract_duration_months: Optional[int] = None
    contractor_name: Optional[str] = None
    contractor_pin: Optional[str] = None
    contractor_nca_license: Optional[str] = None
    document_url: Optional[str] = None
    document_s3_key: Optional[str] = None
    raw_ocr_text: Optional[str] = None
    data_quality: Optional[int] = Field(None, ge=0, le=100)
    extraction_method: Optional[str] = None


class ProcurementRecordResponse(ProcurementRecordBase):
    """Schema for procurement record API responses"""

    procurement_id: int = Field(..., description="Auto-generated procurement ID")
    project_uuid: Optional[UUID] = Field(
        None, description="Reference to parent project"
    )
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


class ProcurementRecordList(BaseModel):
    """Schema for paginated list of procurement records"""

    total: int = Field(..., description="Total number of records")
    page: int = Field(..., description="Current page number", ge=1)
    page_size: int = Field(..., description="Number of records per page", ge=1, le=100)
    records: list[ProcurementRecordResponse] = Field(
        ..., description="List of procurement records"
    )


class ScraperStats(BaseModel):
    """Schema for scraper statistics and monitoring"""

    total_tenders_scraped: int = Field(0, description="Total tenders collected")
    successful_downloads: int = Field(0, description="Successful PDF downloads")
    failed_downloads: int = Field(0, description="Failed PDF downloads")
    duplicates_skipped: int = Field(0, description="Duplicate tenders skipped")
    processing_time_seconds: float = Field(0.0, description="Total processing time")
    last_scrape_timestamp: Optional[datetime] = Field(
        None, description="Timestamp of last scrape"
    )
    errors: list[str] = Field(
        default_factory=list, description="List of errors encountered"
    )


class OCRResult(BaseModel):
    """Schema for OCR extraction results"""

    tender_number: Optional[str] = None
    tender_title: Optional[str] = None
    procuring_entity: Optional[str] = None
    contract_sum: Optional[str] = None
    contractor_name: Optional[str] = None
    award_date: Optional[str] = None
    completion_date: Optional[str] = None
    raw_text: str = Field(..., description="Full OCR text")
    confidence_score: Optional[float] = Field(
        None, description="OCR confidence score 0-100", ge=0, le=100
    )
    extraction_method: str = Field(
        default="aws_textract", description="OCR method used"
    )
