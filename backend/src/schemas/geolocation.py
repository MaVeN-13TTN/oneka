"""
Pydantic schemas for geolocation resources.
"""

from typing import Optional
from pydantic import BaseModel, Field


class GeolocationResolveRequest(BaseModel):
    """Request body for POST /geolocation/resolve."""

    procurement_id: int = Field(..., description="Procurement record to resolve")


class GeolocationResultResponse(BaseModel):
    """Result of a single geolocation resolution."""

    procurement_id: int
    resolved: bool = Field(..., description="Whether GPS was successfully resolved")
    tier: Optional[int] = Field(
        None, description="Resolution tier: 1=eGP, 2=KMHFL fuzzy, 3=ward centroid"
    )
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence: Optional[int] = Field(None, description="GPS quality score 0-100")
    method: Optional[str] = Field(None, description="gps_source tag")
    facility_name: Optional[str] = None
    match_score: Optional[int] = None


class GeolocationCoverageResponse(BaseModel):
    """Coverage breakdown across all procurement records."""

    total: int = Field(..., description="Total procurement records")
    tier1_egp: int = Field(..., description="Records with eGP-embedded GPS")
    tier2_fuzzy: int = Field(..., description="Records resolved via KMHFL fuzzy match")
    tier3_ward: int = Field(..., description="Records resolved via ward centroid")
    unresolved: int = Field(..., description="Records with no GPS resolution yet")
