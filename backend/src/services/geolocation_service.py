"""
Three-tier geolocation resolution pipeline for procurement records.

Tier | Source          | Trigger                                  | GPS Quality
-----|-----------------|------------------------------------------|------------
  1  | eGP embedded    | delivery_latitude already set on record  |  70–90
  2  | KMHFL fuzzy     | spaCy NER → RapidFuzz token_set_ratio    |  60–80
  3  | Ward centroid   | Tier 2 score < 70, use ward centroid     |  20

After resolving, a GeolocationRecord row is created and project.geolocation_status
is updated to "geolocated" when the record is linked to a project.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.geolocation import GeolocationRecord
from src.models.procurement import ProcurementRecord
from src.models.project import Project
from src.models.admin_boundary import AdminBoundary

logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

TIER2_MIN_SCORE = 70   # minimum RapidFuzz score to accept Tier 2 match
TIER3_QUALITY = 20     # GPS quality score assigned to ward centroid fallback
GPS_SOURCE_TIER1 = "EGP_MANUAL_PIN"      # set if locationType == MANUAL
GPS_SOURCE_TIER1_AUTO = "EGP_AUTO_GEOCODED"
GPS_SOURCE_TIER2 = "KMHFL_MATCHED"
GPS_SOURCE_TIER3 = "WARD_CENTROID"

# KMHFL JSON cache written by data/scrapers/kmhfl.py → refresh_kmhfl_task
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_KMHFL_CACHE_PATH = _REPO_ROOT / "data" / "cache" / "kmhfl_facilities.json"

# ── lazy NLP model ─────────────────────────────────────────────────────────────

_nlp = None


def _get_nlp():
    """Load spaCy model once; return None gracefully if not installed."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except (ImportError, OSError):
            logger.warning(
                "spaCy / en_core_web_sm not available — Tier 2 NER degraded to "
                "full-title fuzzy match only."
            )
    return _nlp


# ── KMHFL cache helpers ────────────────────────────────────────────────────────

def _load_kmhfl_facilities() -> list[dict]:
    """Load KMHFL facility list from local JSON cache."""
    if not _KMHFL_CACHE_PATH.exists():
        logger.warning("KMHFL cache not found at %s", _KMHFL_CACHE_PATH)
        return []
    try:
        with open(_KMHFL_CACHE_PATH) as fh:
            raw = json.load(fh)
        # Support both list and {"results": [...]} / {"facilities": [...]} wrappers
        if isinstance(raw, list):
            return raw
        for key in ("results", "facilities", "data"):
            if key in raw and isinstance(raw[key], list):
                return raw[key]
        return []
    except Exception as exc:
        logger.error("Failed to load KMHFL cache: %s", exc)
        return []


def _facility_coords(facility: dict) -> tuple[float, float] | None:
    """Extract (lat, lon) from a KMHFL facility dict, tolerating field name variants."""
    lat = facility.get("lat") or facility.get("latitude")
    lon = facility.get("long") or facility.get("lon") or facility.get("longitude")
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            pass
    return None


def _facility_name(facility: dict) -> str:
    """Return the facility name string."""
    return str(facility.get("name") or facility.get("facility_name") or "")


# ── result dataclass ──────────────────────────────────────────────────────────

@dataclass
class GeolocationResult:
    lat: float
    lon: float
    confidence: int       # 0-100
    method: str           # gps_source tag
    tier: int             # 1, 2, or 3
    facility_name: Optional[str] = None
    facility_code: Optional[str] = None
    match_score: Optional[int] = None


# ── service ───────────────────────────────────────────────────────────────────

class GeolocationService:
    """Resolves GPS location for a procurement record via 3-tier strategy."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._facilities: list[dict] | None = None  # loaded lazily

    # ── public API ────────────────────────────────────────────────────────────

    def resolve(self, procurement_id: int) -> Optional[GeolocationResult]:
        """
        Attempt to resolve GPS location for a procurement record.

        Returns a GeolocationResult and persists a GeolocationRecord row.
        Returns None if all three tiers fail.
        """
        record = (
            self._db.query(ProcurementRecord)
            .filter(ProcurementRecord.procurement_id == procurement_id)
            .first()
        )
        if not record:
            logger.warning("resolve: no procurement record %s", procurement_id)
            return None

        result = (
            self._resolve_tier1(record)
            or self._resolve_tier2(record)
            or self._resolve_tier3(record)
        )

        if result:
            self._persist_result(record, result)

        return result

    def batch_resolve(self, procurement_ids: list[int]) -> dict:
        """
        Resolve GPS for a list of procurement IDs.

        Skips records already resolved at Tier 1 (delivery_latitude set).
        Returns stats dict.
        """
        stats = {"resolved": 0, "failed": 0, "skipped_tier1": 0}
        for pid in procurement_ids:
            record = (
                self._db.query(ProcurementRecord)
                .filter(ProcurementRecord.procurement_id == pid)
                .first()
            )
            if not record:
                stats["failed"] += 1
                continue
            if record.delivery_latitude is not None:
                stats["skipped_tier1"] += 1
                continue
            result = self.resolve(pid)
            if result:
                stats["resolved"] += 1
            else:
                stats["failed"] += 1
        return stats

    def get_coverage_stats(self) -> dict:
        """Return count breakdown of GPS resolution tiers across all records."""
        db = self._db

        def _count(source: str) -> int:
            return (
                db.query(func.count(ProcurementRecord.procurement_id))
                .filter(ProcurementRecord.gps_source == source)
                .scalar()
                or 0
            )

        total = (
            db.query(func.count(ProcurementRecord.procurement_id)).scalar() or 0
        )
        tier1_manual = _count(GPS_SOURCE_TIER1)
        tier1_auto = _count(GPS_SOURCE_TIER1_AUTO)
        tier2 = _count(GPS_SOURCE_TIER2)
        tier3 = _count(GPS_SOURCE_TIER3)
        tier1 = tier1_manual + tier1_auto

        return {
            "total": total,
            "tier1_egp": tier1,
            "tier2_fuzzy": tier2,
            "tier3_ward": tier3,
            "unresolved": max(0, total - tier1 - tier2 - tier3),
        }

    # ── tier implementations ───────────────────────────────────────────────────

    def _resolve_tier1(
        self, record: ProcurementRecord
    ) -> Optional[GeolocationResult]:
        """Tier 1: pass-through if delivery_latitude/longitude already set by EGP scraper."""
        if record.delivery_latitude is None or record.delivery_longitude is None:
            return None

        quality = record.gps_quality_score or 70
        method = record.gps_source or GPS_SOURCE_TIER1_AUTO

        return GeolocationResult(
            lat=float(record.delivery_latitude),
            lon=float(record.delivery_longitude),
            confidence=quality,
            method=method,
            tier=1,
        )

    def _resolve_tier2(
        self, record: ProcurementRecord
    ) -> Optional[GeolocationResult]:
        """
        Tier 2: spaCy NER to extract facility name candidates from tender_title,
        then RapidFuzz token_set_ratio against KMHFL facility list.
        Falls back to matching the full tender_title if NER finds nothing useful.
        """
        if not record.tender_title:
            return None

        facilities = self._load_facilities()
        if not facilities:
            return None

        facility_names = [_facility_name(f) for f in facilities]

        # Candidates: NER entities + full title
        candidates = self._extract_ner_candidates(record.tender_title)
        candidates.append(record.tender_title)

        best_score = 0
        best_facility: Optional[dict] = None

        for candidate in candidates:
            if not candidate.strip():
                continue
            match = process.extractOne(
                candidate,
                facility_names,
                scorer=fuzz.token_set_ratio,
                score_cutoff=TIER2_MIN_SCORE,
            )
            if match and match[1] > best_score:
                best_score = match[1]
                best_facility = facilities[match[2]]

        if best_facility is None:
            return None

        coords = _facility_coords(best_facility)
        if coords is None:
            return None

        lat, lon = coords
        quality = min(80, int(best_score))
        return GeolocationResult(
            lat=lat,
            lon=lon,
            confidence=quality,
            method=GPS_SOURCE_TIER2,
            tier=2,
            facility_name=_facility_name(best_facility),
            facility_code=str(
                best_facility.get("code")
                or best_facility.get("facility_code")
                or ""
            ) or None,
            match_score=int(best_score),
        )

    def _resolve_tier3(
        self, record: ProcurementRecord
    ) -> Optional[GeolocationResult]:
        """
        Tier 3: ward centroid fallback.
        Extracts county/ward hints from procuring_entity and tender_title,
        then queries admin_boundaries for a matching ward centroid.
        """
        hints = self._extract_location_hints(record)
        if not hints:
            return None

        query = self._db.query(AdminBoundary).filter(
            AdminBoundary.centroid_lat.isnot(None),
            AdminBoundary.centroid_lon.isnot(None),
        )

        boundary: Optional[AdminBoundary] = None

        # Try ward match first (most specific), then constituency, then county
        for field, value in hints:
            if field == "ward":
                boundary = (
                    query.filter(
                        func.lower(AdminBoundary.name) == value.lower()
                    ).first()
                )
            elif field == "constituency":
                boundary = (
                    query.filter(
                        func.lower(AdminBoundary.constituency) == value.lower()
                    ).first()
                )
            elif field == "county":
                boundary = (
                    query.filter(
                        func.lower(AdminBoundary.county) == value.lower()
                    ).first()
                )
            if boundary:
                break

        if not boundary:
            return None

        return GeolocationResult(
            lat=float(boundary.centroid_lat),
            lon=float(boundary.centroid_lon),
            confidence=TIER3_QUALITY,
            method=GPS_SOURCE_TIER3,
            tier=3,
            facility_name=f"{boundary.name}, {boundary.county}",
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _load_facilities(self) -> list[dict]:
        """Load and cache KMHFL facility list (once per service lifetime)."""
        if self._facilities is None:
            self._facilities = _load_kmhfl_facilities()
        return self._facilities

    def _extract_ner_candidates(self, text: str) -> list[str]:
        """Return entity spans from text flagged as ORG / GPE / FAC by spaCy."""
        nlp = _get_nlp()
        if nlp is None:
            return []
        doc = nlp(text)
        return [
            ent.text
            for ent in doc.ents
            if ent.label_ in {"ORG", "GPE", "FAC", "LOC"}
        ]

    def _extract_location_hints(
        self, record: ProcurementRecord
    ) -> list[tuple[str, str]]:
        """
        Return a prioritised list of (field, value) location hints extracted
        from procuring_entity and tender_title.
        """
        hints: list[tuple[str, str]] = []
        text_sources = [
            record.procuring_entity or "",
            record.tender_title or "",
        ]
        combined = " ".join(text_sources)

        nlp = _get_nlp()
        if nlp:
            doc = nlp(combined)
            for ent in doc.ents:
                if ent.label_ in {"GPE", "LOC"}:
                    hints.append(("ward", ent.text))
                    hints.append(("constituency", ent.text))
                    hints.append(("county", ent.text))
        else:
            # Degenerate: try splitting procuring_entity on common separators
            for source in text_sources:
                for token in source.replace(",", " ").replace("-", " ").split():
                    if len(token) > 4:
                        hints.append(("county", token))

        return hints

    def _persist_result(
        self, record: ProcurementRecord, result: GeolocationResult
    ) -> None:
        """
        Persist resolved GPS to procurement_records and create a GeolocationRecord.
        Also marks project.geolocation_status = 'geolocated' if linked.
        """
        db = self._db

        # Update GPS fields on the procurement record
        record.delivery_latitude = result.lat  # type: ignore[assignment]
        record.delivery_longitude = result.lon  # type: ignore[assignment]
        record.gps_source = result.method
        record.gps_quality_score = result.confidence

        # Create (or skip duplicate) GeolocationRecord
        existing = (
            db.query(GeolocationRecord)
            .filter(
                GeolocationRecord.project_uuid == record.project_uuid,
                GeolocationRecord.match_method == result.method,
            )
            .first()
        ) if record.project_uuid else None

        if not existing and record.project_uuid is not None:
            geo = GeolocationRecord(
                project_uuid=record.project_uuid,
                source_system="eGP" if result.tier == 1 else (
                    "KMHFL" if result.tier == 2 else "WARD"
                ),
                latitude=result.lat,
                longitude=result.lon,
                match_method=result.method,
                match_score=result.match_score or result.confidence,
                match_confidence=result.confidence,
                facility_name=result.facility_name,
                facility_code=result.facility_code,
            )
            geo.set_geom_from_coordinates()
            db.add(geo)

        # Mark project as geolocated
        if record.project_uuid:
            project = (
                db.query(Project)
                .filter(Project.project_uuid == record.project_uuid)
                .first()
            )
            if project and project.geolocation_status != "geolocated":
                project.geolocation_status = "geolocated"

        db.commit()
        logger.info(
            "Geolocation Tier %d resolved for procurement %s: "
            "lat=%.6f lon=%.6f quality=%d method=%s",
            result.tier,
            record.procurement_id,
            result.lat,
            result.lon,
            result.confidence,
            result.method,
        )
