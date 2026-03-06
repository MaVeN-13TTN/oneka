"""
Section 106B(4) Certificate Service — generate legally admissible PDF
certificates for satellite analysis evidence.

Kenya Evidence Act, Section 106B(4), requires seven fields for electronic
records to be admissible in court:
  1. Source of the electronic record
  2. Scene acquisition timestamp (ISO 8601)
  3. Processing algorithm description
  4. Data integrity proof (SHA-256 hash of original scene file)
  5. Chain of custody (download/processing timestamps, analyst identity)
  6. System operating statement
  7. Signature block for signing official
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from src.config import settings
from src.models.geolocation import GeolocationRecord
from src.models.project import Project
from src.models.satellite import SatelliteAnalysis
from src.services.s3_storage import S3StorageService

logger = logging.getLogger(__name__)

# Template directory: backend/templates/
_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"


class CertificateService:
    """Generate Section 106B(4) PDF certificates for satellite analysis evidence."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.s3_service = S3StorageService()
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )

    def generate_certificate(
        self,
        project_uuid: UUID,
        analyst_name: str,
        analyst_title: str,
    ) -> bytes:
        """
        Generate a Section 106B(4) PDF certificate.

        Returns PDF bytes. Raises LookupError if project not found,
        ValueError if no satellite analyses exist.
        """
        # 1. Fetch project
        project = (
            self.db.query(Project)
            .filter(Project.project_uuid == project_uuid)
            .first()
        )
        if not project:
            raise LookupError(f"Project {project_uuid} not found")

        # 2. Fetch all satellite analyses
        analyses = (
            self.db.query(SatelliteAnalysis)
            .filter(SatelliteAnalysis.project_uuid == project_uuid)
            .order_by(SatelliteAnalysis.acquisition_date.asc())
            .all()
        )
        if not analyses:
            raise ValueError(
                f"No satellite analyses found for project {project_uuid}. "
                "Run satellite analysis before generating a certificate."
            )

        # 3. Fetch geolocation
        geolocation = (
            self.db.query(GeolocationRecord)
            .filter(GeolocationRecord.project_uuid == project_uuid)
            .first()
        )

        # 4. Build per-analysis scene records with SHA-256 hashes
        scene_records = []
        for analysis in analyses:
            scene_hash = self._get_scene_hash(analysis.image_url)
            scene_records.append({
                "sensor": analysis.sensor,
                "scene_id": analysis.scene_id or "N/A",
                "acquisition_date": (
                    analysis.acquisition_date.isoformat()
                    if analysis.acquisition_date else "N/A"
                ),
                "analysis_type": analysis.analysis_type,
                "processing_algorithm": self._describe_algorithm(analysis),
                "processing_date": (
                    analysis.processing_date.isoformat()
                    if analysis.processing_date else "N/A"
                ),
                "cloud_cover": analysis.cloud_cover_percentage,
                "ndvi_mean": (
                    float(analysis.ndvi_mean) if analysis.ndvi_mean is not None else None
                ),
                "sar_vv_mean": (
                    float(analysis.sar_vv_mean) if analysis.sar_vv_mean is not None else None
                ),
                "interpretation": analysis.interpretation,
                "construction_phase": analysis.construction_phase,
                "sha256_hash": scene_hash,
                "image_url": analysis.image_url,
            })

        # 5. Build template context
        context = self._build_context(
            project=project,
            analyses=analyses,
            scene_records=scene_records,
            geolocation=geolocation,
            analyst_name=analyst_name,
            analyst_title=analyst_title,
        )

        # 6. Render HTML
        template = self._jinja_env.get_template("certificate_106b.html")
        html_str = template.render(**context)

        # 7. Convert to PDF
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html_str).write_pdf()

        logger.info(
            "Generated 106B certificate for project %s (%d bytes, %d scenes)",
            project_uuid, len(pdf_bytes), len(scene_records),
        )
        return pdf_bytes

    def store_certificate(
        self,
        project_uuid: UUID,
        pdf_bytes: bytes,
    ) -> Optional[str]:
        """Store the generated PDF in S3. Returns S3 key or None on failure."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"certificate_106b_{timestamp}.pdf"
        s3_key = self.s3_service.upload_pdf_bytes(
            pdf_bytes=pdf_bytes,
            tender_number=str(project_uuid),
            filename=filename,
            metadata={
                "document_type": "106b_certificate",
                "project_uuid": str(project_uuid),
                "generated_at": datetime.utcnow().isoformat(),
                "content_hash": hashlib.sha256(pdf_bytes).hexdigest(),
            },
        )
        if s3_key:
            logger.info("Stored certificate in S3: %s", s3_key)
        return s3_key

    # ── Private helpers ──────────────────────────────────────────────

    def _get_scene_hash(self, image_url: Optional[str]) -> str:
        """Retrieve SHA-256 hash of a scene file from S3 object metadata."""
        if not image_url:
            return "N/A \u2014 no scene file referenced"

        s3_key = self._extract_s3_key(image_url)
        if not s3_key:
            return "N/A \u2014 unable to resolve S3 key"

        metadata = self.s3_service.get_metadata(s3_key)
        if not metadata:
            return "N/A \u2014 metadata unavailable"

        user_metadata = metadata.get("metadata", {})
        return (
            user_metadata.get("file_hash")
            or user_metadata.get("content_hash")
            or "N/A \u2014 hash not recorded in S3 metadata"
        )

    @staticmethod
    def _extract_s3_key(image_url: str) -> Optional[str]:
        """Parse an image URL to extract the S3 object key."""
        if image_url.startswith("s3://"):
            parts = image_url[5:].split("/", 1)
            return parts[1] if len(parts) > 1 else None
        if "s3.amazonaws.com" in image_url:
            from urllib.parse import urlparse
            parsed = urlparse(image_url)
            return parsed.path.lstrip("/")
        # Treat as raw S3 key (e.g., from image_url stored directly)
        if "/" in image_url and not image_url.startswith(("http://", "https://")):
            return image_url
        return None

    @staticmethod
    def _describe_algorithm(analysis: SatelliteAnalysis) -> str:
        """Return a human-readable description of the processing algorithm."""
        algo = analysis.processing_algorithm or "unknown"
        if analysis.analysis_type == "NDVI_change":
            return (
                f"Normalized Difference Vegetation Index (NDVI) computed as "
                f"(NIR \u2212 Red) / (NIR + Red) using Sentinel-2 Band 8 (842 nm) "
                f"and Band 4 (665 nm). Processing engine: {algo}. "
                f"Change detection via temporal linear regression of NDVI "
                f"mean values over the project monitoring period."
            )
        if analysis.analysis_type == "SAR_backscatter":
            return (
                f"Synthetic Aperture Radar (SAR) backscatter analysis using "
                f"Sentinel-1 C-band VV and VH polarisation. Radiometric "
                f"calibration to sigma-nought (dB). Processing engine: {algo}. "
                f"Structural change detected via VV backscatter delta "
                f"relative to pre-construction baseline."
            )
        return f"Analysis type: {analysis.analysis_type}. Processing engine: {algo}."

    def _build_context(
        self,
        project: Project,
        analyses: list[SatelliteAnalysis],
        scene_records: list[dict],
        geolocation: Optional[GeolocationRecord],
        analyst_name: str,
        analyst_title: str,
    ) -> dict:
        """Assemble all 7 Section 106B(4) fields into a Jinja2 context dict."""
        now = datetime.utcnow()
        first_date = analyses[0].acquisition_date
        last_date = analyses[-1].acquisition_date

        return {
            # Certificate metadata
            "certificate_number": (
                f"ONEKA-106B-{str(project.project_uuid)[:8].upper()}"
                f"-{now.strftime('%Y%m%d%H%M%S')}"
            ),
            "generation_date": now.strftime("%d %B %Y"),
            "generation_timestamp": now.isoformat() + "Z",

            # Project information
            "project_uuid": str(project.project_uuid),
            "project_name": project.project_name,
            "project_type": (
                project.project_type.value if project.project_type else "N/A"
            ),
            "county": project.county or "N/A",
            "constituency": project.constituency or "N/A",
            "ward": project.ward or "N/A",
            "estimated_value_kes": (
                f"{float(project.estimated_value_kes):,.2f}"
                if project.estimated_value_kes else "N/A"
            ),
            "risk_level": (
                project.risk_level.value if project.risk_level else "N/A"
            ),
            "risk_score": project.risk_score,
            "ghost_probability": (
                f"{float(project.ghost_probability):.4f}"
                if project.ghost_probability is not None else "N/A"
            ),

            # Geolocation
            "latitude": (
                f"{float(geolocation.latitude):.7f}" if geolocation else "N/A"
            ),
            "longitude": (
                f"{float(geolocation.longitude):.7f}" if geolocation else "N/A"
            ),
            "geolocation_source": (
                geolocation.source_system if geolocation else "N/A"
            ),
            "geolocation_method": (
                geolocation.match_method if geolocation else "N/A"
            ),

            # Field 1: Source of electronic record
            "data_source": "European Space Agency (ESA) Copernicus Data Space Ecosystem",
            "data_source_url": "https://dataspace.copernicus.eu",

            # Field 2: Acquisition timestamps
            "monitoring_period_start": (
                first_date.isoformat() if first_date else "N/A"
            ),
            "monitoring_period_end": (
                last_date.isoformat() if last_date else "N/A"
            ),
            "total_scenes": len(scene_records),

            # Fields 3 & 4: Per-scene records (algorithm + hash)
            "scene_records": scene_records,

            # Field 5: Chain of custody
            "analyst_name": analyst_name,
            "analyst_title": analyst_title,
            "processing_system": "Oneka AI Infrastructure Auditing Platform",
            "processing_system_version": settings.api_version,

            # Field 6: System operating statement
            "system_statement": (
                "The computer system (Oneka AI Infrastructure Auditing Platform) "
                "was operating properly at the time the data described herein was "
                "produced. The system was functioning within normal parameters and "
                "no errors were detected during the processing of the satellite "
                "imagery referenced in this certificate."
            ),

            # Field 7: Signature block
            "signatory_line_1_title": (
                "Certifying Officer, Office of the Auditor General"
            ),
            "signatory_line_2_title": "Technical Analyst, Oneka AI Platform",
        }
