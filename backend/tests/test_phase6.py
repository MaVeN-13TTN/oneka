"""
Phase 6 test suite — Section 106B(4) Legal Certificate Generator.

Coverage targets:
  certificate_service.py   (backend/src/services)  — CertificateService
  certificates.py          (backend/src/routers)    — Certificate router
  certificate_106b.html    (backend/templates)      — Jinja2 template

Test groups:
  1. CertificateService unit tests (algorithm, hash, S3 key parsing)
  2. Certificate generation integration (context, template, PDF)
  3. Certificate router HTTP tests
  4. Certificate S3 storage tests
"""

from __future__ import annotations

import hashlib
from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.models.geolocation import GeolocationRecord
from src.models.project import Project, ProjectStatus, RiskLevel
from src.models.satellite import SatelliteAnalysis


# ── Helpers ─────────────────────────────────────────────────────────────


def _make_project(test_db, *, project_uuid=None, name="Test Road Project",
                  county="Nairobi", risk_level=None):
    p = Project(
        project_uuid=project_uuid or uuid4(),
        project_name=name,
        county=county,
        status=ProjectStatus.ONGOING,
        risk_level=risk_level,
    )
    test_db.add(p)
    test_db.commit()
    test_db.refresh(p)
    return p


def _make_satellite_analysis(test_db, project_uuid, *,
                              sensor="Sentinel-2",
                              acquisition_date="2024-06-15",
                              analysis_type="NDVI_change",
                              image_url="s3://oneka-bucket/scenes/test.tif",
                              processing_algorithm="rasterio",
                              processing_date="2024-06-16",
                              scene_id="S2A_MSIL2A_20240615T073611"):
    sa = SatelliteAnalysis(
        project_uuid=project_uuid,
        sensor=sensor,
        acquisition_date=acquisition_date,
        analysis_type=analysis_type,
        image_url=image_url,
        processing_algorithm=processing_algorithm,
        processing_date=processing_date,
        scene_id=scene_id,
        ndvi_mean=0.45,
        ndvi_std=0.12,
    )
    test_db.add(sa)
    test_db.commit()
    test_db.refresh(sa)
    return sa


def _make_geolocation(test_db, project_uuid, *, lat=-1.2921, lon=36.8219):
    g = GeolocationRecord(
        project_uuid=project_uuid,
        latitude=lat,
        longitude=lon,
        match_method="egp_manual",
        match_confidence=95,
        source_system="KMHFL",
    )
    test_db.add(g)
    test_db.commit()
    test_db.refresh(g)
    return g


# =============================================================================
# Group 1 — CertificateService Unit Tests
# =============================================================================


class TestCertificateServiceUnit:
    """Unit tests for individual CertificateService methods."""

    def test_generate_raises_lookup_error_missing_project(self, test_db):
        """LookupError for non-existent project UUID."""
        from src.services.certificate_service import CertificateService
        svc = CertificateService(test_db)
        with pytest.raises(LookupError, match="not found"):
            svc.generate_certificate(uuid4(), "Analyst", "Title")

    def test_generate_raises_value_error_no_analyses(self, test_db):
        """ValueError when project exists but has no satellite analyses."""
        from src.services.certificate_service import CertificateService
        project = _make_project(test_db)
        svc = CertificateService(test_db)
        with pytest.raises(ValueError, match="No satellite analyses"):
            svc.generate_certificate(project.project_uuid, "Analyst", "Title")

    def test_describe_algorithm_ndvi(self):
        """NDVI analysis returns NDVI formula description."""
        from src.services.certificate_service import CertificateService
        analysis = MagicMock()
        analysis.analysis_type = "NDVI_change"
        analysis.processing_algorithm = "rasterio"
        desc = CertificateService._describe_algorithm(analysis)
        assert "NDVI" in desc
        assert "NIR" in desc
        assert "rasterio" in desc

    def test_describe_algorithm_sar(self):
        """SAR analysis returns SAR backscatter description."""
        from src.services.certificate_service import CertificateService
        analysis = MagicMock()
        analysis.analysis_type = "SAR_backscatter"
        analysis.processing_algorithm = "pyrosar"
        desc = CertificateService._describe_algorithm(analysis)
        assert "SAR" in desc
        assert "VV" in desc
        assert "pyrosar" in desc

    def test_describe_algorithm_generic(self):
        """Unknown analysis type returns generic description."""
        from src.services.certificate_service import CertificateService
        analysis = MagicMock()
        analysis.analysis_type = "RGB_inspection"
        analysis.processing_algorithm = "custom"
        desc = CertificateService._describe_algorithm(analysis)
        assert "RGB_inspection" in desc
        assert "custom" in desc

    def test_extract_s3_key_from_s3_url(self):
        """Parse s3://bucket/key format."""
        from src.services.certificate_service import CertificateService
        key = CertificateService._extract_s3_key("s3://my-bucket/path/to/file.tif")
        assert key == "path/to/file.tif"

    def test_extract_s3_key_from_https_url(self):
        """Parse https://bucket.s3.amazonaws.com/key format."""
        from src.services.certificate_service import CertificateService
        key = CertificateService._extract_s3_key(
            "https://my-bucket.s3.amazonaws.com/scenes/test.tif"
        )
        assert key == "scenes/test.tif"

    def test_extract_s3_key_returns_none_for_unknown_format(self):
        """Unrecognized URL format returns None."""
        from src.services.certificate_service import CertificateService
        key = CertificateService._extract_s3_key("https://example.com/file.tif")
        assert key is None

    def test_get_scene_hash_returns_hash_from_metadata(self, test_db):
        """SHA-256 hash extracted from S3 metadata."""
        from src.services.certificate_service import CertificateService
        svc = CertificateService(test_db)
        expected_hash = "a" * 64
        with patch.object(svc.s3_service, "get_metadata") as mock_meta:
            mock_meta.return_value = {
                "size": 1024,
                "last_modified": "2024-06-16T00:00:00Z",
                "content_type": "image/tiff",
                "metadata": {"file_hash": expected_hash},
            }
            result = svc._get_scene_hash("s3://bucket/scene.tif")
            assert result == expected_hash

    def test_get_scene_hash_returns_na_when_no_url(self, test_db):
        """None image_url returns N/A string."""
        from src.services.certificate_service import CertificateService
        svc = CertificateService(test_db)
        result = svc._get_scene_hash(None)
        assert "N/A" in result


# =============================================================================
# Group 2 — Certificate Generation Integration
# =============================================================================


class TestCertificateGeneration:
    """Integration tests for certificate template rendering and PDF output."""

    def test_generate_certificate_returns_pdf_bytes(self, test_db):
        """generate_certificate() returns non-empty bytes (mocked WeasyPrint)."""
        from src.services.certificate_service import CertificateService
        project = _make_project(test_db, name="Nairobi Hospital Upgrade",
                                risk_level=RiskLevel.HIGH)
        _make_satellite_analysis(test_db, project.project_uuid)
        _make_geolocation(test_db, project.project_uuid)

        svc = CertificateService(test_db)
        with patch.object(svc.s3_service, "get_metadata") as mock_meta:
            mock_meta.return_value = {"metadata": {"file_hash": "a" * 64}}
            mock_pdf = b"%PDF-1.4 fake pdf content"
            mock_wp = MagicMock()
            mock_wp.HTML.return_value.write_pdf.return_value = mock_pdf
            with patch.dict("sys.modules", {"weasyprint": mock_wp}):
                pdf_bytes = svc.generate_certificate(
                    project.project_uuid, "John Doe", "Senior Analyst"
                )

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes.startswith(b"%PDF")

    def test_template_contains_all_seven_fields(self, test_db):
        """Context dict contains all 7 Section 106B(4) fields."""
        from src.services.certificate_service import CertificateService
        project = _make_project(test_db, name="Mombasa Road Extension")
        sa = _make_satellite_analysis(test_db, project.project_uuid)

        svc = CertificateService(test_db)
        scene_records = [{
            "sensor": "Sentinel-2", "scene_id": "test",
            "acquisition_date": "2024-06-15", "analysis_type": "NDVI_change",
            "processing_algorithm": "NDVI formula desc",
            "processing_date": "2024-06-16", "cloud_cover": 10,
            "ndvi_mean": 0.45, "sar_vv_mean": None,
            "interpretation": None, "construction_phase": None,
            "sha256_hash": "b" * 64, "image_url": "s3://bucket/test.tif",
        }]

        context = svc._build_context(
            project=project,
            analyses=[sa],
            scene_records=scene_records,
            geolocation=None,
            analyst_name="Jane Smith",
            analyst_title="GIS Analyst",
        )

        # Field 1: Source
        assert "Copernicus" in context["data_source"]
        # Field 2: Timestamps
        assert context["monitoring_period_start"]
        # Field 3 & 4: Scene records with algorithm + hash
        assert len(context["scene_records"]) > 0
        assert context["scene_records"][0]["sha256_hash"]
        # Field 5: Chain of custody
        assert context["analyst_name"] == "Jane Smith"
        # Field 6: System statement
        assert "operating properly" in context["system_statement"]
        # Field 7: Signature block
        assert context["signatory_line_1_title"]

    def test_certificate_includes_project_details(self, test_db):
        """Context includes project name, county, risk_level."""
        from src.services.certificate_service import CertificateService
        project = _make_project(
            test_db, name="Kisumu Fish Market",
            county="Kisumu", risk_level=RiskLevel.CRITICAL,
        )
        sa = _make_satellite_analysis(test_db, project.project_uuid)

        svc = CertificateService(test_db)
        context = svc._build_context(
            project=project,
            analyses=[sa],
            scene_records=[{
                "sensor": "S2", "sha256_hash": "N/A", "scene_id": "x",
                "acquisition_date": "2024-01-01", "analysis_type": "NDVI_change",
                "processing_algorithm": "...", "processing_date": "2024-01-02",
                "cloud_cover": 5, "ndvi_mean": 0.3, "sar_vv_mean": None,
                "interpretation": None, "construction_phase": None,
                "image_url": None,
            }],
            geolocation=None,
            analyst_name="Test", analyst_title="Test",
        )
        assert context["project_name"] == "Kisumu Fish Market"
        assert context["county"] == "Kisumu"
        assert context["risk_level"] == "CRITICAL"

    def test_certificate_multiple_analyses(self, test_db):
        """Handles multiple satellite analyses for one project."""
        from src.services.certificate_service import CertificateService
        project = _make_project(test_db)
        _make_satellite_analysis(test_db, project.project_uuid,
                                  acquisition_date="2024-03-01",
                                  scene_id="SCENE_A")
        _make_satellite_analysis(test_db, project.project_uuid,
                                  acquisition_date="2024-06-01",
                                  scene_id="SCENE_B",
                                  sensor="Sentinel-1",
                                  analysis_type="SAR_backscatter")

        svc = CertificateService(test_db)
        with patch.object(svc.s3_service, "get_metadata") as mock_meta:
            mock_meta.return_value = {"metadata": {"file_hash": "c" * 64}}
            mock_wp = MagicMock()
            mock_wp.HTML.return_value.write_pdf.return_value = b"%PDF"
            with patch.dict("sys.modules", {"weasyprint": mock_wp}):
                pdf = svc.generate_certificate(
                    project.project_uuid, "Analyst", "Title"
                )
        assert len(pdf) > 0


# =============================================================================
# Group 3 — Certificate Router
# =============================================================================


class TestCertificateRouter:
    """Tests for /api/v1/certificates/ endpoints."""

    def test_generate_certificate_404_unknown_project(self, client):
        """Non-existent project -> 404."""
        resp = client.get(
            f"/api/v1/certificates/{uuid4()}",
            params={"analyst_name": "Test User", "analyst_title": "Analyst"},
        )
        assert resp.status_code == 404

    def test_generate_certificate_422_no_analyses(self, client, test_db):
        """Project with no satellite data -> 422."""
        project = _make_project(test_db)
        resp = client.get(
            f"/api/v1/certificates/{project.project_uuid}",
            params={"analyst_name": "Test User", "analyst_title": "Analyst"},
        )
        assert resp.status_code == 422

    def test_generate_certificate_422_missing_analyst_name(self, client, test_db):
        """Missing required analyst_name -> 422 validation error."""
        project = _make_project(test_db)
        resp = client.get(
            f"/api/v1/certificates/{project.project_uuid}",
            params={"analyst_title": "Analyst"},
        )
        assert resp.status_code == 422

    def test_generate_certificate_returns_pdf(self, client, test_db):
        """Successful generation -> 200 with application/pdf."""
        project = _make_project(test_db, risk_level=RiskLevel.HIGH)
        _make_satellite_analysis(test_db, project.project_uuid)

        with patch("src.services.certificate_service.CertificateService") as MockSvc:
            mock_instance = MagicMock()
            mock_instance.generate_certificate.return_value = b"%PDF-1.4 test content"
            mock_instance.store_certificate.return_value = "certificates/test.pdf"
            MockSvc.return_value = mock_instance

            resp = client.get(
                f"/api/v1/certificates/{project.project_uuid}",
                params={"analyst_name": "Test User", "analyst_title": "Senior Analyst"},
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert b"%PDF" in resp.content

    def test_certificate_status_endpoint(self, client, test_db):
        """GET /certificates/{uuid}/status returns can_generate flag."""
        project = _make_project(test_db)
        _make_satellite_analysis(test_db, project.project_uuid)

        resp = client.get(f"/api/v1/certificates/{project.project_uuid}/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["can_generate"] is True
        assert data["satellite_analyses_count"] == 1

    def test_certificate_status_no_analyses(self, client, test_db):
        """Status returns can_generate=false when no analyses exist."""
        project = _make_project(test_db)

        resp = client.get(f"/api/v1/certificates/{project.project_uuid}/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["can_generate"] is False
        assert data["satellite_analyses_count"] == 0

    def test_certificate_status_404_unknown_project(self, client):
        """Status for non-existent project -> 404."""
        resp = client.get(f"/api/v1/certificates/{uuid4()}/status")
        assert resp.status_code == 404


# =============================================================================
# Group 4 — Certificate S3 Storage
# =============================================================================


class TestCertificateStorage:
    """Tests for certificate S3 storage."""

    def test_store_certificate_calls_s3_upload(self, test_db):
        """store_certificate() calls S3StorageService.upload_pdf_bytes."""
        from src.services.certificate_service import CertificateService
        svc = CertificateService(test_db)
        pdf_bytes = b"%PDF-1.4 test"
        project_uuid = uuid4()

        with patch.object(svc.s3_service, "upload_pdf_bytes") as mock_upload:
            mock_upload.return_value = f"tenders/2024/03/{project_uuid}/cert.pdf"
            s3_key = svc.store_certificate(project_uuid, pdf_bytes)

        assert s3_key is not None
        mock_upload.assert_called_once()
        call_kwargs = mock_upload.call_args
        assert call_kwargs[1]["metadata"]["document_type"] == "106b_certificate"

    def test_store_certificate_returns_none_on_s3_failure(self, test_db):
        """S3 upload failure returns None (graceful degradation)."""
        from src.services.certificate_service import CertificateService
        svc = CertificateService(test_db)

        with patch.object(svc.s3_service, "upload_pdf_bytes") as mock_upload:
            mock_upload.return_value = None
            result = svc.store_certificate(uuid4(), b"%PDF")

        assert result is None

    def test_store_certificate_metadata_contains_hash(self, test_db):
        """Stored certificate metadata includes content_hash."""
        from src.services.certificate_service import CertificateService
        svc = CertificateService(test_db)
        pdf_bytes = b"%PDF-1.4 test content for hashing"
        expected_hash = hashlib.sha256(pdf_bytes).hexdigest()

        with patch.object(svc.s3_service, "upload_pdf_bytes") as mock_upload:
            mock_upload.return_value = "some/key.pdf"
            svc.store_certificate(uuid4(), pdf_bytes)

        call_kwargs = mock_upload.call_args
        assert call_kwargs[1]["metadata"]["content_hash"] == expected_hash
