"""
Section 106B(4) certificate router — Phase 6.

Endpoints:
  GET /api/v1/certificates/{project_uuid}
      Generate and return a PDF certificate for the project's satellite
      analysis evidence. Stores a copy in S3 automatically.

  GET /api/v1/certificates/{project_uuid}/status
      Check whether a certificate can be generated (satellite data exists).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.project import Project
from src.models.satellite import SatelliteAnalysis
from src.rate_limit import limiter

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/certificates/{project_uuid}",
    summary="Generate Section 106B(4) certificate",
    description=(
        "Generate a legally admissible PDF certificate under Kenya's Evidence "
        "Act Section 106B(4) for all satellite analyses associated with the "
        "project. The certificate is stored in S3 and returned as a PDF download."
    ),
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF certificate"},
        404: {"description": "Project not found"},
        422: {"description": "No satellite analyses for project"},
    },
)
@limiter.limit("10/minute")
async def generate_certificate(
    request: Request,
    project_uuid: UUID,
    analyst_name: str = Query(
        ..., min_length=2, max_length=200,
        description="Full name of the certifying analyst",
    ),
    analyst_title: str = Query(
        ..., min_length=2, max_length=200,
        description="Official title of the certifying analyst",
    ),
    db: Session = Depends(get_db),
):
    """Generate and return a 106B(4) PDF certificate."""
    from src.services.certificate_service import CertificateService

    try:
        service = CertificateService(db)

        # Generate PDF
        pdf_bytes = service.generate_certificate(
            project_uuid=project_uuid,
            analyst_name=analyst_name,
            analyst_title=analyst_title,
        )

        # Store in S3 (non-blocking; failure does not prevent PDF return)
        try:
            s3_key = service.store_certificate(project_uuid, pdf_bytes)
            if s3_key:
                logger.info("Certificate stored in S3: %s", s3_key)
        except Exception as exc:
            logger.warning(
                "Failed to store certificate in S3 for %s: %s",
                project_uuid, exc,
            )

        # Return PDF as streaming response
        filename = f"certificate_106b_{project_uuid}.pdf"
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except ImportError as exc:
        logger.error("WeasyPrint not installed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PDF generation dependencies not installed (weasyprint)",
        )


@router.get(
    "/certificates/{project_uuid}/status",
    summary="Check certificate readiness",
    description="Check if a 106B(4) certificate can be generated for this project.",
)
async def certificate_status(
    project_uuid: UUID,
    db: Session = Depends(get_db),
):
    """Check if satellite data exists for certificate generation."""
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

    analyses_count = (
        db.query(SatelliteAnalysis)
        .filter(SatelliteAnalysis.project_uuid == project_uuid)
        .count()
    )

    return {
        "project_uuid": str(project_uuid),
        "satellite_analyses_count": analyses_count,
        "can_generate": analyses_count > 0,
        "message": (
            "Certificate can be generated"
            if analyses_count > 0
            else "No satellite analyses \u2014 run satellite analysis first"
        ),
    }
