"""
Concordance service — fuzzy-links procurement + financial records to Project rows.

Responsibilities:
  1. link_procurement_to_project  — matches tender_title → Project.project_name
  2. link_financial_to_project    — matches programme → Project.project_name
  3. get_project_truth_record     — returns unified project card (all linked data)
  4. reconcile_all_unlinked       — batch-links all orphaned procurement records

Fuzzy matching uses RapidFuzz token_set_ratio:
  - procurement → project:  score >= 85 required
  - financial   → project:  score >= 80 required

When no existing project matches, a new Project is created from the procurement
record data (project_type inferred from title keywords, county from entity name).
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from uuid import UUID

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from src.models.financial import FinancialRecord
from src.models.procurement import ProcurementRecord
from src.models.project import Project, ProjectStatus, ProjectType
from src.services.geolocation_service import GeolocationService

logger = logging.getLogger(__name__)

# ── thresholds ────────────────────────────────────────────────────────────────

PROCUREMENT_MATCH_THRESHOLD = 85
FINANCIAL_MATCH_THRESHOLD = 80

# ── keyword → project_type inference ─────────────────────────────────────────

_TYPE_KEYWORDS: list[tuple[ProjectType, list[str]]] = [
    (
        ProjectType.HEALTH,
        ["hospital", "health centre", "dispensary", "clinic", "nursing",
         "maternity", "pharmacy", "laboratory", "ICU", "theatre"],
    ),
    (
        ProjectType.EDUCATION,
        ["school", "classroom", "laboratory", "college", "university",
         "polytechnic", "library", "dormitory", "staffroom"],
    ),
    (
        ProjectType.ROADS,
        ["road", "bridge", "highway", "street", "junction", "flyover",
         "culvert", "tarmac", "pavement", "walkway"],
    ),
    (
        ProjectType.WATER,
        ["water", "borehole", "dam", "irrigation", "tank", "pipeline",
         "well", "sewage", "drainage", "sanitation"],
    ),
    (
        ProjectType.MARKETS,
        ["market", "trading", "commercial", "stall", "kiosk"],
    ),
]

# Kenya's 47 county names (lower-case) for extraction from procuring_entity
_KENYA_COUNTIES = [
    "mombasa", "kwale", "kilifi", "tana river", "lamu", "taita taveta",
    "garissa", "wajir", "mandera", "marsabit", "isiolo", "meru",
    "tharaka nithi", "embu", "kitui", "machakos", "makueni", "nyandarua",
    "nyeri", "kirinyaga", "murang'a", "kiambu", "turkana", "west pokot",
    "samburu", "trans nzoia", "uasin gishu", "elgeyo marakwet", "nandi",
    "baringo", "laikipia", "nakuru", "narok", "kajiado", "kericho",
    "bomet", "kakamega", "vihiga", "bungoma", "busia", "siaya",
    "kisumu", "homa bay", "migori", "kisii", "nyamira", "nairobi",
]


def _infer_project_type(title: str) -> ProjectType:
    """Return ProjectType enum inferred from title keywords, default OTHER."""
    title_lower = title.lower()
    for project_type, keywords in _TYPE_KEYWORDS:
        if any(kw in title_lower for kw in keywords):
            return project_type
    return ProjectType.OTHER


def _extract_county(text: str) -> Optional[str]:
    """Return the first Kenya county name found in text (title-cased), or None."""
    text_lower = text.lower()
    for county in _KENYA_COUNTIES:
        # word-boundary match to avoid false positives like "kisii" inside "nakisii"
        if re.search(r"\b" + re.escape(county) + r"\b", text_lower):
            return county.title()
    return None


# ── service ───────────────────────────────────────────────────────────────────

class ConcordanceService:
    """Links procurement and financial records to canonical Project rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── public API ────────────────────────────────────────────────────────────

    def link_procurement_to_project(
        self, procurement_id: int
    ) -> Optional[UUID]:
        """
        Fuzzy-match a procurement record to an existing Project row.

        If no match exists (score < 85), a new Project is auto-created.
        After linking, GeolocationService.resolve() is called.

        Returns the project_uuid that the record was linked to.
        """
        record = (
            self._db.query(ProcurementRecord)
            .filter(ProcurementRecord.procurement_id == procurement_id)
            .first()
        )
        if not record:
            logger.warning("link_procurement: no record with id=%s", procurement_id)
            return None

        if record.project_uuid is not None:
            return record.project_uuid  # already linked

        if not record.tender_title:
            return None

        project_uuid = (
            self._find_matching_project(record.tender_title, PROCUREMENT_MATCH_THRESHOLD)
            or self._create_project_from_procurement(record)
        )

        record.project_uuid = project_uuid  # type: ignore[assignment]
        self._db.commit()
        logger.info(
            "Procurement %s linked to project %s", procurement_id, project_uuid
        )

        # Resolve geolocation now that the record has a project_uuid
        GeolocationService(self._db).resolve(procurement_id)

        return project_uuid

    def link_financial_to_project(
        self, financial_id: int
    ) -> Optional[UUID]:
        """
        Fuzzy-match a financial record's programme/ministry to a Project.

        Minimum score: 80.  Records below threshold are left unlinked.
        Returns project_uuid if linked, else None.
        """
        record = (
            self._db.query(FinancialRecord)
            .filter(FinancialRecord.financial_id == financial_id)
            .first()
        )
        if not record:
            return None

        if record.project_uuid is not None:
            return record.project_uuid  # already linked

        search_text = " ".join(
            filter(None, [record.programme, record.ministry, record.department])
        )
        if not search_text.strip():
            return None

        project_uuid = self._find_matching_project(
            search_text, FINANCIAL_MATCH_THRESHOLD
        )
        if not project_uuid:
            return None

        record.project_uuid = project_uuid  # type: ignore[assignment]
        record.match_method = "concordance_fuzzy"
        self._db.commit()
        logger.info(
            "Financial %s linked to project %s", financial_id, project_uuid
        )
        return project_uuid

    def get_project_truth_record(self, project_uuid: UUID) -> Optional[dict]:
        """
        Return the unified 'project card' for a given project UUID.

        Includes the canonical project fields plus all linked procurement,
        financial, geolocation, and satellite records.
        """
        project = (
            self._db.query(Project)
            .filter(Project.project_uuid == project_uuid)
            .first()
        )
        if not project:
            return None

        lead_geo = (
            project.geolocation_records[0] if project.geolocation_records else None
        )

        return {
            "project_uuid": str(project.project_uuid),
            "project_name": project.project_name,
            "project_type": project.project_type.value if project.project_type else None,
            "county": project.county,
            "constituency": project.constituency,
            "ward": project.ward,
            "status": project.status.value,
            "risk_level": project.risk_level.value if project.risk_level else None,
            "risk_score": project.risk_score,
            "estimated_value_kes": (
                float(project.estimated_value_kes)
                if project.estimated_value_kes
                else None
            ),
            "geolocation_status": project.geolocation_status,
            "location": {
                "latitude": float(lead_geo.latitude) if lead_geo else None,
                "longitude": float(lead_geo.longitude) if lead_geo else None,
                "method": lead_geo.match_method if lead_geo else None,
                "confidence": lead_geo.match_confidence if lead_geo else None,
            },
            "procurement": [
                {
                    "procurement_id": r.procurement_id,
                    "tender_number": r.tender_number,
                    "tender_title": r.tender_title,
                    "source_system": r.source_system,
                    "contract_sum_kes": (
                        float(r.contract_sum_kes) if r.contract_sum_kes else None
                    ),
                    "award_date": r.award_date.isoformat() if r.award_date else None,
                    "contractor_name": r.contractor_name,
                }
                for r in project.procurement_records
            ],
            "financial": [
                {
                    "financial_id": f.financial_id,
                    "fiscal_year": f.fiscal_year,
                    "ministry": f.ministry,
                    "programme": f.programme,
                    "budget_allocated_kes": (
                        float(f.budget_allocated_kes)
                        if f.budget_allocated_kes
                        else None
                    ),
                    "budget_absorbed_kes": (
                        float(f.budget_absorbed_kes)
                        if f.budget_absorbed_kes
                        else None
                    ),
                    "absorption_rate": (
                        float(f.absorption_rate) if f.absorption_rate else None
                    ),
                }
                for f in project.financial_records
            ],
            "satellite_analyses_count": len(project.satellite_analyses),
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
        }

    def reconcile_all_unlinked(self) -> dict:
        """
        Batch-link all procurement records that have no project_uuid.

        Returns stats: {linked, created_new, failed, total_processed}.
        """
        unlinked = (
            self._db.query(ProcurementRecord)
            .filter(ProcurementRecord.project_uuid.is_(None))
            .filter(ProcurementRecord.tender_title.isnot(None))
            .all()
        )
        stats = {"linked": 0, "created_new": 0, "failed": 0, "total_processed": 0}
        existing_count_before = self._db.query(Project).count()

        for record in unlinked:
            stats["total_processed"] += 1
            try:
                result_uuid = self.link_procurement_to_project(
                    record.procurement_id
                )
                if result_uuid:
                    stats["linked"] += 1
                else:
                    stats["failed"] += 1
            except Exception as exc:
                logger.error(
                    "reconcile failed for procurement %s: %s",
                    record.procurement_id,
                    exc,
                )
                stats["failed"] += 1

        new_projects = self._db.query(Project).count() - existing_count_before
        stats["created_new"] = new_projects
        return stats

    # ── private helpers ───────────────────────────────────────────────────────

    def _find_matching_project(
        self, text: str, threshold: int
    ) -> Optional[UUID]:
        """
        Query all project names, run RapidFuzz token_set_ratio against `text`,
        return project_uuid of best match if score >= threshold.
        """
        projects = self._db.query(
            Project.project_uuid, Project.project_name
        ).all()
        if not projects:
            return None

        names = [p.project_name for p in projects]
        match = process.extractOne(
            text,
            names,
            scorer=fuzz.token_set_ratio,
            score_cutoff=threshold,
        )
        if not match:
            return None

        matched_name = match[0]
        for p in projects:
            if p.project_name == matched_name:
                return p.project_uuid
        return None

    def _create_project_from_procurement(
        self, record: ProcurementRecord
    ) -> UUID:
        """Auto-create a Project row from a procurement record's metadata."""
        title = record.tender_title or f"Project {record.tender_number}"

        entity_text = " ".join(
            filter(None, [record.procuring_entity, record.tender_title])
        )
        county = _extract_county(entity_text)

        project = Project(
            project_name=title,
            project_type=_infer_project_type(title),
            county=county,
            estimated_value_kes=record.contract_sum_kes,
            status=ProjectStatus.AWARDED,
            geolocation_status="not_geolocated",
        )
        self._db.add(project)
        self._db.flush()  # populate project_uuid before commit
        logger.info(
            "Created new project %s from procurement %s",
            project.project_uuid,
            record.procurement_id,
        )
        return project.project_uuid
