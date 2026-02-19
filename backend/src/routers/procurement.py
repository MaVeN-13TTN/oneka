"""
Procurement API endpoints - CRUD operations for tender/procurement records.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import logging

from src.database import get_db
from src.schemas.procurement import (
    ProcurementRecordCreate,
    ProcurementRecordUpdate,
    ProcurementRecordResponse,
    ProcurementRecordList,
    ScraperStats,
)
from src.services.procurement_service import ProcurementService


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/procurement",
    response_model=ProcurementRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create procurement record",
    description="Create a new procurement/tender record in the database",
)
async def create_procurement_record(
    procurement_data: ProcurementRecordCreate, db: Session = Depends(get_db)
):
    """Create a new procurement record"""
    try:
        service = ProcurementService(db)
        record = service.create_procurement_record(procurement_data)
        return record
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating procurement record: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create procurement record",
        )


@router.get(
    "/procurement",
    response_model=ProcurementRecordList,
    summary="List procurement records",
    description="Get paginated list of procurement records with optional filtering",
)
async def list_procurement_records(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Records per page"),
    source_system: Optional[str] = Query(None, description="Filter by source system"),
    procuring_entity: Optional[str] = Query(
        None, description="Filter by procuring entity"
    ),
    search: Optional[str] = Query(
        None, description="Search in tender number, title, contractor"
    ),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    db: Session = Depends(get_db),
):
    """Get paginated list of procurement records"""
    service = ProcurementService(db)

    # Calculate skip based on page
    skip = (page - 1) * page_size

    records, total = service.get_procurement_records(
        skip=skip,
        limit=page_size,
        source_system=source_system,
        procuring_entity=procuring_entity,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return ProcurementRecordList(
        total=total,
        page=page,
        page_size=page_size,
        records=[ProcurementRecordResponse.model_validate(r) for r in records],
    )


@router.get(
    "/procurement/search",
    response_model=ProcurementRecordResponse,
    summary="Get procurement by tender number",
    description="Retrieve procurement record by tender number using query parameter",
)
async def get_procurement_by_tender_number(
    tender_number: str = Query(..., description="Tender number to search for"),
    db: Session = Depends(get_db),
):
    """Get procurement record by tender number"""
    service = ProcurementService(db)
    record = service.get_by_tender_number(tender_number)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender {tender_number} not found",
        )

    return record


@router.post(
    "/procurement/scrape",
    response_model=ScraperStats,
    summary="Scrape PPIP tenders",
    description="Trigger PPIP scraper to collect tenders and store in database",
)
async def scrape_ppip_tenders(
    max_pages: int = Query(5, ge=1, le=20, description="Maximum pages to scrape"),
    download_pdfs: bool = Query(True, description="Download and upload PDFs to S3"),
    db: Session = Depends(get_db),
):
    """
    Scrape tenders from PPIP and store in database.

    This endpoint triggers the web scraper to collect tender data from the
    Public Procurement Information Portal. PDFs can optionally be downloaded
    and uploaded to S3.
    """
    try:
        service = ProcurementService(db)
        stats = service.scrape_and_store_tenders(
            max_pages=max_pages, download_pdfs=download_pdfs
        )
        return stats
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scraping failed: {str(e)}",
        )


@router.get(
    "/procurement/stats/summary",
    summary="Get procurement statistics",
    description="Get summary statistics for procurement records",
)
async def get_procurement_statistics(db: Session = Depends(get_db)):
    """Get procurement statistics"""
    service = ProcurementService(db)
    return service.get_statistics()


@router.get(
    "/procurement/{procurement_id}",
    response_model=ProcurementRecordResponse,
    summary="Get procurement record",
    description="Retrieve a single procurement record by ID",
)
async def get_procurement_record(procurement_id: int, db: Session = Depends(get_db)):
    """Get procurement record by ID"""
    service = ProcurementService(db)
    record = service.get_procurement_record(procurement_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Procurement record {procurement_id} not found",
        )

    return record


@router.put(
    "/procurement/{procurement_id}",
    response_model=ProcurementRecordResponse,
    summary="Update procurement record",
    description="Update an existing procurement record",
)
async def update_procurement_record(
    procurement_id: int,
    update_data: ProcurementRecordUpdate,
    db: Session = Depends(get_db),
):
    """Update procurement record"""
    service = ProcurementService(db)
    record = service.update_procurement_record(procurement_id, update_data)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Procurement record {procurement_id} not found",
        )

    return record


@router.delete(
    "/procurement/{procurement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete procurement record",
    description="Delete a procurement record and its associated S3 documents",
)
async def delete_procurement_record(procurement_id: int, db: Session = Depends(get_db)):
    """Delete procurement record"""
    service = ProcurementService(db)
    success = service.delete_procurement_record(procurement_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Procurement record {procurement_id} not found",
        )

    return None
