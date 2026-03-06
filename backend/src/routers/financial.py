"""
Financial API endpoints.

GET /api/v1/financial/{project_uuid}            — all financial records for project
GET /api/v1/financial/{project_uuid}/absorption — absorption gap analysis
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.financial import FinancialRecord
from src.models.project import Project
from src.services.financial_service import FinancialService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/financial/{project_uuid}",
    summary="Financial records for project",
    description="Return all COB/IFMIS financial records linked to a project.",
)
async def get_financial_records(
    project_uuid: UUID, db: Session = Depends(get_db)
):
    """Return all financial records for a given project UUID."""
    project = (
        db.query(Project)
        .filter(Project.project_uuid == project_uuid)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_uuid} not found",
        )

    service = FinancialService(db)
    records = service.get_financial_records_for_project(project_uuid)

    return {
        "project_uuid": str(project_uuid),
        "project_name": project.project_name,
        "count": len(records),
        "records": [
            {
                "financial_id": r.financial_id,
                "source_system": r.source_system,
                "fiscal_year": r.fiscal_year,
                "ministry": r.ministry,
                "department": r.department,
                "programme": r.programme,
                "budget_allocated_kes": (
                    float(r.budget_allocated_kes) if r.budget_allocated_kes else None
                ),
                "budget_released_kes": (
                    float(r.budget_released_kes) if r.budget_released_kes else None
                ),
                "budget_absorbed_kes": (
                    float(r.budget_absorbed_kes) if r.budget_absorbed_kes else None
                ),
                "absorption_rate": (
                    float(r.absorption_rate) if r.absorption_rate else None
                ),
                "reporting_period": r.reporting_period,
                "document_source": r.document_source,
            }
            for r in records
        ],
    }


@router.get(
    "/financial/{project_uuid}/absorption",
    summary="Absorption gap analysis",
    description=(
        "Calculate the budget absorption gap for a project: "
        "total allocated vs. total absorbed across all financial periods."
    ),
)
async def get_absorption_gap(
    project_uuid: UUID, db: Session = Depends(get_db)
):
    """Return absorption gap metrics for a project."""
    project = (
        db.query(Project)
        .filter(Project.project_uuid == project_uuid)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_uuid} not found",
        )

    service = FinancialService(db)
    gap = service.calculate_absorption_gap(project_uuid)

    return {
        "project_uuid": str(project_uuid),
        "project_name": project.project_name,
        **gap,
    }
