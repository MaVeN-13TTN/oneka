"""
Pydantic schemas for Project resources.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectResponse(BaseModel):
    """Single project row."""

    project_uuid: UUID
    project_name: str
    project_type: Optional[str] = None
    county: Optional[str] = None
    constituency: Optional[str] = None
    ward: Optional[str] = None
    status: str
    risk_level: Optional[str] = None
    risk_score: Optional[int] = None
    confidence_score: Optional[int] = None
    estimated_value_kes: Optional[Decimal] = None
    geolocation_status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    """Paginated list of projects."""

    total: int
    page: int
    page_size: int
    projects: list[ProjectResponse]


class ProjectTruthRecord(BaseModel):
    """Unified project card — all linked data sources in one response."""

    project_uuid: str
    project_name: str
    project_type: Optional[str] = None
    county: Optional[str] = None
    constituency: Optional[str] = None
    ward: Optional[str] = None
    status: str
    risk_level: Optional[str] = None
    risk_score: Optional[int] = None
    estimated_value_kes: Optional[float] = None
    geolocation_status: str
    location: dict[str, Any] = Field(default_factory=dict)
    procurement: list[dict[str, Any]] = Field(default_factory=list)
    financial: list[dict[str, Any]] = Field(default_factory=list)
    satellite_analyses_count: int = 0
    created_at: str
    updated_at: str


class ReconcileResponse(BaseModel):
    """Result of POST /projects/reconcile."""

    linked: int = Field(..., description="Records linked to existing projects")
    created_new: int = Field(..., description="New projects created")
    failed: int = Field(..., description="Records that could not be linked")
    total_processed: int
