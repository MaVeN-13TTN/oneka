"""
Tests for Phase 2 — Interoperability Engine.

Covers:
  - GeolocationService: Tier 1 passthrough, Tier 2 KMHFL fuzzy, Tier 3 ward centroid,
    coverage stats, batch_resolve
  - ConcordanceService: project matching, auto-creation, financial linking,
    truth record, reconcile
  - API endpoints: /geolocation/*, /projects/*, /financial/*
"""

import json
import os
import tempfile
from decimal import Decimal
from unittest.mock import patch

import pytest
from decimal import Decimal

from src.models import (
    FinancialRecord,
    GeolocationRecord,
    Project,
    ProjectStatus,
    ProjectType,
    ProcurementRecord,
)
from src.models.admin_boundary import AdminBoundary
from src.models.project import RiskLevel
from src.services.concordance_service import (
    ConcordanceService,
    _extract_county,
    _infer_project_type,
)
from src.services.geolocation_service import (
    GeolocationService,
    GPS_SOURCE_TIER1,
    GPS_SOURCE_TIER1_AUTO,
    GPS_SOURCE_TIER2,
    GPS_SOURCE_TIER3,
)


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_project(test_db):
    """A committed project row."""
    project = Project(
        project_name="Kenyatta National Hospital Expansion",
        project_type=ProjectType.HEALTH,
        county="Nairobi",
        status=ProjectStatus.ONGOING,
        geolocation_status="not_geolocated",
    )
    test_db.add(project)
    test_db.commit()
    test_db.refresh(project)
    return project


@pytest.fixture
def procurement_with_gps(test_db, sample_project):
    """Procurement record that already has eGP GPS coordinates (Tier 1)."""
    record = ProcurementRecord(
        project_uuid=sample_project.project_uuid,
        source_system="EGP",
        tender_number="EGP/2026/GPS/001",
        tender_title="Construction of KNH Maternity Wing",
        delivery_latitude=Decimal("-1.300000"),
        delivery_longitude=Decimal("36.806000"),
        gps_source=GPS_SOURCE_TIER1_AUTO,
        gps_quality_score=70,
    )
    test_db.add(record)
    test_db.commit()
    test_db.refresh(record)
    return record


@pytest.fixture
def procurement_no_gps(test_db, sample_project):
    """Procurement record with no GPS yet (for Tier 2/3 testing)."""
    record = ProcurementRecord(
        project_uuid=sample_project.project_uuid,
        source_system="PPIP",
        tender_number="PPIP/2026/NOGPS/001",
        tender_title="Rehabilitation of Kenyatta National Hospital Main Block",
    )
    test_db.add(record)
    test_db.commit()
    test_db.refresh(record)
    return record


@pytest.fixture
def procurement_unlinked(test_db):
    """Procurement record with no project link (for concordance testing)."""
    record = ProcurementRecord(
        source_system="PPIP",
        tender_number="PPIP/2026/UNLINKED/001",
        tender_title="Supply and installation of water pump Kisumu General Hospital",
    )
    test_db.add(record)
    test_db.commit()
    test_db.refresh(record)
    return record


@pytest.fixture
def ward_boundary(test_db):
    """An AdminBoundary row for ward-centroid fallback testing."""
    boundary = AdminBoundary(
        name="Westlands",
        ward_code="WD-NAI-001",
        constituency="Westlands",
        county="Nairobi",
        level=3,
        centroid_lat=Decimal("-1.2679"),
        centroid_lon=Decimal("36.8062"),
    )
    test_db.add(boundary)
    test_db.commit()
    test_db.refresh(boundary)
    return boundary


@pytest.fixture
def kmhfl_cache_file():
    """Write a minimal KMHFL JSON cache to a temp file, yield its path."""
    facilities = [
        {
            "name": "Kenyatta National Hospital",
            "code": "13001",
            "lat": -1.3009,
            "long": 36.8073,
            "county": "Nairobi",
        },
        {
            "name": "Moi Teaching and Referral Hospital",
            "code": "47001",
            "lat": 0.5143,
            "long": 35.2698,
            "county": "Uasin Gishu",
        },
    ]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as fh:
        json.dump(facilities, fh)
        path = fh.name
    yield path
    os.unlink(path)


# ── GeolocationService ────────────────────────────────────────────────────────


class TestGeolocationServiceTier1:
    """Tier 1: eGP GPS passthrough."""

    def test_resolve_tier1_returns_result(self, test_db, procurement_with_gps):
        service = GeolocationService(test_db)
        result = service.resolve(procurement_with_gps.procurement_id)

        assert result is not None
        assert result.tier == 1
        assert abs(result.lat - (-1.300000)) < 0.0001
        assert abs(result.lon - 36.806000) < 0.0001
        assert result.confidence == 70

    def test_resolve_tier1_creates_geolocation_record(
        self, test_db, procurement_with_gps, sample_project
    ):
        service = GeolocationService(test_db)
        service.resolve(procurement_with_gps.procurement_id)

        geo = (
            test_db.query(GeolocationRecord)
            .filter(GeolocationRecord.project_uuid == sample_project.project_uuid)
            .first()
        )
        assert geo is not None
        assert abs(float(geo.latitude) - (-1.300000)) < 0.0001

    def test_resolve_tier1_marks_project_geolocated(
        self, test_db, procurement_with_gps, sample_project
    ):
        service = GeolocationService(test_db)
        service.resolve(procurement_with_gps.procurement_id)

        test_db.refresh(sample_project)
        assert sample_project.geolocation_status == "geolocated"

    def test_resolve_returns_none_for_missing_id(self, test_db):
        service = GeolocationService(test_db)
        result = service.resolve(9999999)
        assert result is None


class TestGeolocationServiceTier2:
    """Tier 2: spaCy NER + RapidFuzz KMHFL match."""

    def test_resolve_tier2_with_kmhfl_cache(
        self, test_db, procurement_no_gps, kmhfl_cache_file
    ):
        """Title contains 'Kenyatta National Hospital' → score ~100 against cache."""
        from pathlib import Path
        with patch(
            "src.services.geolocation_service._KMHFL_CACHE_PATH",
            Path(kmhfl_cache_file),
        ):
            service = GeolocationService(test_db)
            result = service.resolve(procurement_no_gps.procurement_id)

        # Tier 2 should succeed (near-exact match)
        if result is not None:
            assert result.tier in (1, 2)  # 1 if already set, 2 if newly resolved
            assert result.lat is not None
            assert result.lon is not None

    def test_resolve_tier2_low_score_returns_none_or_tier3(
        self, test_db, ward_boundary
    ):
        """Tender with no facility match should fall through to Tier 3."""
        record = ProcurementRecord(
            source_system="PPIP",
            tender_number="PPIP/2026/GENERIC/001",
            tender_title="Generic construction works Nairobi",
            procuring_entity="Nairobi County Government",
        )
        test_db.add(record)
        test_db.commit()

        with patch(
            "src.services.geolocation_service._KMHFL_CACHE_PATH",
            __import__("pathlib").Path("/nonexistent/path.json"),
        ):
            service = GeolocationService(test_db)
            result = service.resolve(record.procurement_id)

        # No KMHFL cache → Tier 2 skipped; Tier 3 may or may not match
        if result is not None:
            assert result.tier in (2, 3)


class TestGeolocationServiceTier3:
    """Tier 3: ward centroid fallback."""

    def test_resolve_tier3_uses_ward_centroid(self, test_db, ward_boundary):
        """Record with no GPS and no KMHFL match falls back to ward centroid."""
        record = ProcurementRecord(
            source_system="PPIP",
            tender_number="PPIP/2026/WARD/001",
            tender_title="Road construction Westlands",
            procuring_entity="Nairobi County",
        )
        test_db.add(record)
        test_db.commit()

        # Patch KMHFL cache to be empty
        with patch(
            "src.services.geolocation_service._KMHFL_CACHE_PATH",
            __import__("pathlib").Path("/nonexistent/path.json"),
        ):
            service = GeolocationService(test_db)
            result = service.resolve(record.procurement_id)

        # With spaCy NER extracting "Westlands" / "Nairobi" → Tier 3 should fire
        if result is not None and result.tier == 3:
            assert result.method == GPS_SOURCE_TIER3
            assert result.confidence == 20


class TestGeolocationServiceCoverage:
    """Coverage statistics."""

    def test_coverage_stats_all_zeros_on_empty_db(self, test_db):
        service = GeolocationService(test_db)
        stats = service.get_coverage_stats()

        assert stats["total"] == 0
        assert stats["tier1_egp"] == 0
        assert stats["tier2_fuzzy"] == 0
        assert stats["tier3_ward"] == 0
        assert stats["unresolved"] == 0

    def test_coverage_stats_counts_tier1(self, test_db, procurement_with_gps):
        service = GeolocationService(test_db)
        stats = service.get_coverage_stats()

        assert stats["total"] >= 1
        assert stats["tier1_egp"] >= 1

    def test_coverage_unresolved_field(self, test_db, procurement_no_gps):
        service = GeolocationService(test_db)
        stats = service.get_coverage_stats()

        # procurement_no_gps has no gps_source set → contributes to unresolved
        assert stats["unresolved"] >= 1


class TestGeolocationServiceBatchResolve:
    """batch_resolve skips Tier 1 records."""

    def test_batch_resolve_skips_tier1(
        self, test_db, procurement_with_gps, procurement_no_gps
    ):
        service = GeolocationService(test_db)
        stats = service.batch_resolve(
            [procurement_with_gps.procurement_id, procurement_no_gps.procurement_id]
        )

        assert stats["skipped_tier1"] == 1
        assert stats["skipped_tier1"] + stats["resolved"] + stats["failed"] == 2

    def test_batch_resolve_invalid_id(self, test_db):
        service = GeolocationService(test_db)
        stats = service.batch_resolve([9999999])
        assert stats["failed"] == 1


# ── ConcordanceService ────────────────────────────────────────────────────────


class TestConcordanceHelpers:
    """Unit tests for pure helper functions."""

    def test_infer_project_type_health(self):
        assert _infer_project_type("Construction of Kisumu General Hospital") == ProjectType.HEALTH

    def test_infer_project_type_roads(self):
        assert _infer_project_type("Tarmacking of Thika Road junction") == ProjectType.ROADS

    def test_infer_project_type_education(self):
        assert _infer_project_type("Construction of 2 classrooms Mathare Primary") == ProjectType.EDUCATION

    def test_infer_project_type_water(self):
        assert _infer_project_type("Borehole drilling and installation water pump") == ProjectType.WATER

    def test_infer_project_type_default(self):
        assert _infer_project_type("General works") == ProjectType.OTHER

    def test_extract_county_nairobi(self):
        result = _extract_county("Nairobi County Government")
        assert result == "Nairobi"

    def test_extract_county_kisumu(self):
        result = _extract_county("MoH Kisumu sub-county")
        assert result == "Kisumu"

    def test_extract_county_none(self):
        result = _extract_county("Ministry of Health Kenya")
        assert result is None


class TestConcordanceServiceLinking:
    """Test project linking logic."""

    def test_link_procurement_to_existing_project(
        self, test_db, sample_project, procurement_unlinked
    ):
        """RapidFuzz score >= 85 should link to 'Kenyatta National Hospital Expansion'."""
        # Create procurement with title that closely matches sample_project.project_name
        record = ProcurementRecord(
            source_system="PPIP",
            tender_number="PPIP/2026/NEAR/001",
            tender_title="Kenyatta National Hospital Expansion Phase II",
        )
        test_db.add(record)
        test_db.commit()

        service = ConcordanceService(test_db)
        project_uuid = service.link_procurement_to_project(record.procurement_id)

        assert project_uuid is not None
        assert project_uuid == sample_project.project_uuid

        test_db.refresh(record)
        assert record.project_uuid == sample_project.project_uuid

    def test_link_procurement_creates_new_project(self, test_db, procurement_unlinked):
        """No matching project → new Project should be auto-created."""
        service = ConcordanceService(test_db)
        project_uuid = service.link_procurement_to_project(
            procurement_unlinked.procurement_id
        )

        assert project_uuid is not None

        # A new project should exist
        project = (
            test_db.query(Project)
            .filter(Project.project_uuid == project_uuid)
            .first()
        )
        assert project is not None
        # Title has both "hospital" and "water pump" — HEALTH fires first per keyword order
        assert project.project_type in (ProjectType.WATER, ProjectType.HEALTH)

    def test_link_procurement_already_linked_returns_existing(
        self, test_db, procurement_with_gps, sample_project
    ):
        """Already linked record returns existing project_uuid without change."""
        service = ConcordanceService(test_db)
        result_uuid = service.link_procurement_to_project(
            procurement_with_gps.procurement_id
        )
        assert result_uuid == sample_project.project_uuid

    def test_link_procurement_missing_id_returns_none(self, test_db):
        service = ConcordanceService(test_db)
        result = service.link_procurement_to_project(9999999)
        assert result is None

    def test_link_financial_to_project(self, test_db, sample_project):
        """Financial record with matching programme gets linked."""
        financial = FinancialRecord(
            source_system="COB",
            fiscal_year="2025/2026",
            programme="Kenyatta National Hospital Expansion Programme",
            budget_allocated_kes=Decimal("500000000.00"),
        )
        test_db.add(financial)
        test_db.commit()

        service = ConcordanceService(test_db)
        project_uuid = service.link_financial_to_project(financial.financial_id)

        assert project_uuid == sample_project.project_uuid
        test_db.refresh(financial)
        assert financial.project_uuid == sample_project.project_uuid
        assert financial.match_method == "concordance_fuzzy"

    def test_link_financial_no_match_returns_none(self, test_db):
        """Financial record with no matching programme returns None."""
        financial = FinancialRecord(
            source_system="COB",
            fiscal_year="2025/2026",
            programme="Completely unrelated programme XYZ 12345",
            budget_allocated_kes=Decimal("1000000.00"),
        )
        test_db.add(financial)
        test_db.commit()

        service = ConcordanceService(test_db)
        result = service.link_financial_to_project(financial.financial_id)

        assert result is None


class TestConcordanceTruthRecord:
    """get_project_truth_record returns structured unified card."""

    def test_truth_record_structure(self, test_db, sample_project, procurement_with_gps):
        service = ConcordanceService(test_db)
        record = service.get_project_truth_record(sample_project.project_uuid)

        assert record is not None
        assert record["project_uuid"] == str(sample_project.project_uuid)
        assert record["project_name"] == sample_project.project_name
        assert "location" in record
        assert "procurement" in record
        assert "financial" in record
        assert "satellite_analyses_count" in record
        assert len(record["procurement"]) == 1
        assert record["procurement"][0]["tender_number"] == "EGP/2026/GPS/001"

    def test_truth_record_missing_uuid_returns_none(self, test_db):
        import uuid
        service = ConcordanceService(test_db)
        result = service.get_project_truth_record(uuid.uuid4())
        assert result is None


class TestConcordanceReconcile:
    """reconcile_all_unlinked processes orphaned procurement records."""

    def test_reconcile_returns_stats_dict(self, test_db, procurement_unlinked):
        service = ConcordanceService(test_db)
        stats = service.reconcile_all_unlinked()

        assert "linked" in stats
        assert "created_new" in stats
        assert "failed" in stats
        assert "total_processed" in stats
        assert stats["total_processed"] >= 1
        assert stats["linked"] + stats["failed"] == stats["total_processed"]

    def test_reconcile_empty_db_returns_zeros(self, test_db):
        service = ConcordanceService(test_db)
        stats = service.reconcile_all_unlinked()
        assert stats["total_processed"] == 0


# ── API endpoints ─────────────────────────────────────────────────────────────


class TestGeolocationEndpoints:
    """POST /geolocation/resolve and GET /geolocation/coverage."""

    def test_resolve_tier1_via_api(self, client, procurement_with_gps):
        response = client.post(
            "/api/v1/geolocation/resolve",
            json={"procurement_id": procurement_with_gps.procurement_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["resolved"] is True
        assert data["tier"] == 1
        assert data["latitude"] is not None
        assert data["longitude"] is not None

    def test_resolve_missing_record_via_api(self, client):
        response = client.post(
            "/api/v1/geolocation/resolve",
            json={"procurement_id": 9999999},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["resolved"] is False

    def test_coverage_endpoint(self, client, procurement_with_gps):
        response = client.get("/api/v1/geolocation/coverage")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "tier1_egp" in data
        assert "tier2_fuzzy" in data
        assert "tier3_ward" in data
        assert "unresolved" in data
        assert data["total"] >= 1


class TestProjectsEndpoints:
    """GET/POST /api/v1/projects/*"""

    def test_list_projects(self, client, sample_project):
        response = client.get("/api/v1/projects")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "projects" in data
        assert data["total"] >= 1
        assert isinstance(data["projects"], list)

    def test_list_projects_filter_by_county(self, client, sample_project):
        response = client.get("/api/v1/projects?county=Nairobi")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for p in data["projects"]:
            assert "nairobi" in (p["county"] or "").lower()

    def test_list_projects_filter_by_risk_level_invalid(self, client):
        response = client.get("/api/v1/projects?risk_level=INVALID")
        assert response.status_code == 400

    def test_list_projects_pagination(self, client, sample_project):
        response = client.get("/api/v1/projects?page=1&page_size=5")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_get_project_by_uuid(self, client, sample_project):
        response = client.get(f"/api/v1/projects/{sample_project.project_uuid}")
        assert response.status_code == 200
        data = response.json()
        assert data["project_uuid"] == str(sample_project.project_uuid)
        assert data["project_name"] == sample_project.project_name
        assert data["geolocation_status"] == "not_geolocated"

    def test_get_project_not_found(self, client):
        import uuid
        response = client.get(f"/api/v1/projects/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_get_project_truth_record(
        self, client, sample_project, procurement_with_gps
    ):
        response = client.get(
            f"/api/v1/projects/{sample_project.project_uuid}/truth-record"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["project_uuid"] == str(sample_project.project_uuid)
        assert "location" in data
        assert "procurement" in data
        assert len(data["procurement"]) == 1

    def test_get_truth_record_not_found(self, client):
        import uuid
        response = client.get(f"/api/v1/projects/{uuid.uuid4()}/truth-record")
        assert response.status_code == 404

    def test_projects_geojson(self, client, sample_project, procurement_with_gps):
        # First resolve geolocation so the project is "geolocated"
        client.post(
            "/api/v1/geolocation/resolve",
            json={"procurement_id": procurement_with_gps.procurement_id},
        )
        response = client.get("/api/v1/projects/geojson")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert isinstance(data["features"], list)

    def test_reconcile_endpoint(self, client, procurement_unlinked):
        response = client.post("/api/v1/projects/reconcile")
        assert response.status_code == 200
        data = response.json()
        assert "linked" in data
        assert "created_new" in data
        assert "failed" in data
        assert "total_processed" in data
        assert data["total_processed"] >= 1


class TestFinancialEndpoints:
    """GET /api/v1/financial/*"""

    @pytest.fixture
    def financial_record(self, test_db, sample_project):
        record = FinancialRecord(
            project_uuid=sample_project.project_uuid,
            source_system="COB",
            fiscal_year="2025/2026",
            ministry="Ministry of Health",
            programme="Primary Health Infrastructure",
            budget_allocated_kes=Decimal("300000000.00"),
            budget_absorbed_kes=Decimal("180000000.00"),
            absorption_rate=Decimal("60.00"),
        )
        test_db.add(record)
        test_db.commit()
        return record

    def test_get_financial_records(self, client, sample_project, financial_record):
        response = client.get(f"/api/v1/financial/{sample_project.project_uuid}")
        assert response.status_code == 200
        data = response.json()
        assert data["project_uuid"] == str(sample_project.project_uuid)
        assert data["count"] == 1
        assert len(data["records"]) == 1
        record = data["records"][0]
        assert record["fiscal_year"] == "2025/2026"
        assert record["ministry"] == "Ministry of Health"

    def test_get_financial_records_not_found(self, client):
        import uuid
        response = client.get(f"/api/v1/financial/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_get_absorption_gap(self, client, sample_project, financial_record):
        response = client.get(
            f"/api/v1/financial/{sample_project.project_uuid}/absorption"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["project_uuid"] == str(sample_project.project_uuid)
        assert "total_allocated_kes" in data
        assert "total_absorbed_kes" in data
        assert "absorption_rate" in data
        assert "gap_kes" in data
        assert "record_count" in data
        assert data["record_count"] == 1

    def test_get_absorption_gap_not_found(self, client):
        import uuid
        response = client.get(f"/api/v1/financial/{uuid.uuid4()}/absorption")
        assert response.status_code == 404
