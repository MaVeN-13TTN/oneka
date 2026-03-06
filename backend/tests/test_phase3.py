"""
Phase 3 test suite — Satellite Processing Pipeline.

Tests:
  - SatelliteAnalysis / Project model field additions (ndvi_slope, ghost_probability)
  - SatelliteService: result persistence, time-series, NDVI slope regression
  - DivergenceService: physical progress scoring, alert levels, DB side-effects
  - Satellite router endpoints: queue, status, divergence, heat-map
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.models.financial import FinancialRecord
from src.models.geolocation import GeolocationRecord
from src.models.project import Project, ProjectStatus, ProjectType, RiskLevel
from src.models.satellite import SatelliteAnalysis
from src.services.divergence_service import DivergenceService
from src.services.satellite_service import SatelliteService


# ─── shared fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def sample_project(test_db) -> Project:
    """A committed Project with Nairobi county."""
    project = Project(
        project_uuid=uuid.uuid4(),
        project_name="Kenyatta National Hospital Expansion",
        project_type=ProjectType.HEALTH,
        county="Nairobi",
        status=ProjectStatus.ONGOING,
    )
    test_db.add(project)
    test_db.commit()
    test_db.refresh(project)
    return project


@pytest.fixture
def project_with_geolocation(test_db, sample_project):
    """sample_project plus a GeolocationRecord (Nairobi CBD)."""
    geo = GeolocationRecord(
        project_uuid=sample_project.project_uuid,
        source_system="KMHFL",
        latitude=Decimal("-1.2921"),
        longitude=Decimal("36.8219"),
        match_confidence=85,
        match_method="KMHFL_FUZZY",
    )
    test_db.add(geo)
    test_db.commit()
    return sample_project, geo


@pytest.fixture
def financial_record(test_db, sample_project) -> FinancialRecord:
    """A FinancialRecord with 60 % absorption rate."""
    rec = FinancialRecord(
        project_uuid=sample_project.project_uuid,
        source_system="COB",
        fiscal_year="2023/2024",
        programme="KNH Infrastructure Upgrades",
        budget_allocated_kes=Decimal("10000000"),
        budget_absorbed_kes=Decimal("6000000"),
        absorption_rate=Decimal("60.0"),
        match_method="FUZZY",
        confidence_score=80,
    )
    test_db.add(rec)
    test_db.commit()
    return rec


@pytest.fixture
def ndvi_analysis(test_db, sample_project) -> SatelliteAnalysis:
    """A single NDVI_change SatelliteAnalysis row."""
    a = SatelliteAnalysis(
        project_uuid=sample_project.project_uuid,
        sensor="Sentinel-2",
        acquisition_date=date(2024, 1, 15),
        scene_id="S2A_MSIL2A_20240115_T37MBN",
        analysis_type="NDVI_change",
        ndvi_mean=Decimal("0.52"),
        ndvi_std=Decimal("0.08"),
        ndvi_min=Decimal("0.30"),
        ndvi_max=Decimal("0.75"),
    )
    test_db.add(a)
    test_db.commit()
    test_db.refresh(a)
    return a


@pytest.fixture
def ndvi_series(test_db, sample_project) -> list[SatelliteAnalysis]:
    """
    Three NDVI_change rows with declining NDVI (simulating land clearing).
    Dates spaced ~2 months apart; NDVI drops 0.10 per epoch.
    """
    rows = []
    base_date = date(2023, 8, 1)
    ndvi_values = [0.60, 0.50, 0.40]

    for i, ndvi_val in enumerate(ndvi_values):
        a = SatelliteAnalysis(
            project_uuid=sample_project.project_uuid,
            sensor="Sentinel-2",
            acquisition_date=base_date + timedelta(days=60 * i),
            scene_id=f"S2A_MSIL2A_2023{8 + i:02d}01_T37MBN",
            analysis_type="NDVI_change",
            ndvi_mean=Decimal(str(ndvi_val)),
        )
        test_db.add(a)
        rows.append(a)

    test_db.commit()
    for r in rows:
        test_db.refresh(r)
    return rows


@pytest.fixture
def sar_analysis(test_db, sample_project) -> SatelliteAnalysis:
    """A single SAR_backscatter SatelliteAnalysis row."""
    a = SatelliteAnalysis(
        project_uuid=sample_project.project_uuid,
        sensor="Sentinel-1",
        acquisition_date=date(2024, 2, 10),
        scene_id="S1A_IW_GRDH_20240210",
        analysis_type="SAR_backscatter",
        sar_vv_mean=Decimal("-12.5"),
        sar_vh_mean=Decimal("-19.3"),
        sar_backscatter_delta=Decimal("4.2"),  # strong new-structure signal
    )
    test_db.add(a)
    test_db.commit()
    test_db.refresh(a)
    return a


# ─── 1. Model field additions ─────────────────────────────────────────────────


class TestSatelliteModelFields:
    def test_satellite_analysis_has_ndvi_slope_column(self, test_db, sample_project):
        """ndvi_slope can be written and read back."""
        a = SatelliteAnalysis(
            project_uuid=sample_project.project_uuid,
            sensor="Sentinel-2",
            acquisition_date=date(2024, 3, 1),
            analysis_type="NDVI_change",
            ndvi_mean=Decimal("0.45"),
            ndvi_slope=Decimal("-0.0350"),
        )
        test_db.add(a)
        test_db.commit()
        test_db.refresh(a)
        assert a.ndvi_slope is not None
        assert float(a.ndvi_slope) == pytest.approx(-0.0350, rel=1e-4)

    def test_satellite_analysis_has_sar_backscatter_delta_column(
        self, test_db, sample_project
    ):
        """sar_backscatter_delta can be written and read back."""
        a = SatelliteAnalysis(
            project_uuid=sample_project.project_uuid,
            sensor="Sentinel-1",
            acquisition_date=date(2024, 3, 5),
            analysis_type="SAR_backscatter",
            sar_vv_mean=Decimal("-14.0"),
            sar_backscatter_delta=Decimal("3.10"),
        )
        test_db.add(a)
        test_db.commit()
        test_db.refresh(a)
        assert float(a.sar_backscatter_delta) == pytest.approx(3.10, rel=1e-4)

    def test_project_has_ghost_probability_column(self, test_db):
        """ghost_probability can be written and read back."""
        project = Project(
            project_uuid=uuid.uuid4(),
            project_name="Suspiciously Paper-Only School",
            project_type=ProjectType.EDUCATION,
            county="Nairobi",
            status=ProjectStatus.ONGOING,
            ghost_probability=Decimal("0.8750"),
        )
        test_db.add(project)
        test_db.commit()
        test_db.refresh(project)
        assert project.ghost_probability is not None
        assert float(project.ghost_probability) == pytest.approx(0.8750, rel=1e-4)

    def test_project_ghost_probability_nullable(self, test_db):
        """ghost_probability defaults to NULL."""
        project = Project(
            project_uuid=uuid.uuid4(),
            project_name="Normal Road Project",
            project_type=ProjectType.ROADS,
            county="Mombasa",
            status=ProjectStatus.AWARDED,
        )
        test_db.add(project)
        test_db.commit()
        test_db.refresh(project)
        assert project.ghost_probability is None


# ─── 2. SatelliteService ──────────────────────────────────────────────────────


class TestSatelliteServiceQueueAnalysis:
    def test_queue_analysis_raises_lookup_error_when_project_missing(
        self, test_db
    ):
        service = SatelliteService(test_db)
        with pytest.raises(LookupError, match="not found"):
            service.queue_analysis(uuid.uuid4())

    def test_queue_analysis_raises_value_error_when_no_geolocation(
        self, test_db, sample_project
    ):
        service = SatelliteService(test_db)
        with pytest.raises(ValueError, match="no geolocation"):
            service.queue_analysis(sample_project.project_uuid)

    def test_queue_analysis_returns_task_id(
        self, test_db, project_with_geolocation
    ):
        """Mock celery_app.send_task; verify returned task_id."""
        project, _geo = project_with_geolocation
        mock_result = MagicMock()
        mock_result.id = "mock-task-00001"

        with patch("src.celery_app.celery_app") as mock_app:
            mock_app.send_task.return_value = mock_result
            service = SatelliteService(test_db)
            task_id = service.queue_analysis(project.project_uuid)

        assert task_id == "mock-task-00001"
        mock_app.send_task.assert_called_once()
        call_args = mock_app.send_task.call_args
        assert call_args[0][0] == "src.tasks.satellite_tasks.analyse_project_task"


class TestSatelliteServicePersistence:
    def test_save_ndvi_result_creates_row(self, test_db, sample_project):
        """save_ndvi_result() inserts a SatelliteAnalysis row."""
        result = {
            "scene_id": "S2A_MSIL2A_20240301",
            "sensor": "Sentinel-2",
            "statistics": {"mean": 0.48, "std": 0.07, "min": 0.20, "max": 0.70},
            "geotiff_path": "/tmp/S2A_NDVI.tif",
            "visualization_path": "/tmp/S2A_NDVI.png",
        }
        service = SatelliteService(test_db)
        analysis = service.save_ndvi_result(
            sample_project.project_uuid,
            result,
            acquisition_date=date(2024, 3, 1),
        )
        assert analysis.analysis_id is not None
        assert analysis.analysis_type == "NDVI_change"
        assert float(analysis.ndvi_mean) == pytest.approx(0.48, rel=1e-3)
        assert analysis.sensor == "Sentinel-2"

    def test_save_ndvi_result_handles_nan_statistics(
        self, test_db, sample_project
    ):
        """NaN statistics should be stored as NULL, not raise."""
        import math

        result = {
            "scene_id": "S2B_CLOUDY",
            "statistics": {
                "mean": float("nan"),
                "std": float("nan"),
                "min": float("nan"),
                "max": float("nan"),
            },
        }
        service = SatelliteService(test_db)
        analysis = service.save_ndvi_result(
            sample_project.project_uuid, result
        )
        assert analysis.ndvi_mean is None
        assert analysis.ndvi_std is None

    def test_save_sar_result_creates_row(self, test_db, sample_project):
        """save_sar_result() inserts a SAR_backscatter row."""
        result = {
            "scene_id": "S1A_IW_GRD_20240310",
            "sensor": "Sentinel-1",
            "backscatter": {
                "VV": {"mean": -13.4, "std": 2.1},
                "VH": {"mean": -20.2, "std": 2.5},
            },
        }
        service = SatelliteService(test_db)
        analysis = service.save_sar_result(
            sample_project.project_uuid, result, date(2024, 3, 10)
        )
        assert analysis.analysis_type == "SAR_backscatter"
        assert float(analysis.sar_vv_mean) == pytest.approx(-13.4, rel=1e-3)
        assert analysis.sar_backscatter_delta is None  # no baseline provided

    def test_save_sar_result_computes_delta_when_baseline_provided(
        self, test_db, sample_project
    ):
        """sar_backscatter_delta = current_vv - baseline_vv."""
        result = {
            "scene_id": "S1A_IW_GRD_20240410",
            "backscatter": {"VV": {"mean": -10.5}},
        }
        service = SatelliteService(test_db)
        analysis = service.save_sar_result(
            sample_project.project_uuid,
            result,
            date(2024, 4, 10),
            baseline_vv=-15.0,
        )
        # delta = -10.5 - (-15.0) = 4.5
        assert float(analysis.sar_backscatter_delta) == pytest.approx(4.5, rel=1e-3)


class TestSatelliteServiceTimeSeries:
    def test_get_time_series_returns_rows_sorted_by_date(
        self, test_db, ndvi_series
    ):
        """get_time_series() returns rows in ascending acquisition_date order."""
        project_uuid = ndvi_series[0].project_uuid
        service = SatelliteService(test_db)
        series = service.get_time_series(project_uuid)
        assert len(series) == 3
        dates = [r.acquisition_date for r in series]
        assert dates == sorted(dates)

    def test_get_analyses_count(self, test_db, ndvi_series):
        service = SatelliteService(test_db)
        count = service.get_analyses_count(ndvi_series[0].project_uuid)
        assert count == 3

    def test_get_time_series_empty_for_no_rows(self, test_db, sample_project):
        service = SatelliteService(test_db)
        series = service.get_time_series(sample_project.project_uuid)
        assert series == []


class TestSatelliteServiceNDVISlope:
    def test_compute_ndvi_slope_returns_none_for_single_scene(
        self, test_db, ndvi_analysis
    ):
        """Single scene → cannot compute slope → returns None."""
        service = SatelliteService(test_db)
        slope = service.compute_ndvi_slope(ndvi_analysis.project_uuid)
        assert slope is None

    def test_compute_ndvi_slope_negative_for_declining_ndvi(
        self, test_db, ndvi_series
    ):
        """Declining NDVI (0.60 → 0.50 → 0.40 over ~4 months) → slope < 0."""
        service = SatelliteService(test_db)
        slope = service.compute_ndvi_slope(ndvi_series[0].project_uuid)
        assert slope is not None
        assert slope < 0.0

    def test_compute_ndvi_slope_persisted_to_analysis_rows(
        self, test_db, ndvi_series
    ):
        """After compute_ndvi_slope(), each NDVI row has ndvi_slope set."""
        service = SatelliteService(test_db)
        slope = service.compute_ndvi_slope(ndvi_series[0].project_uuid)
        assert slope is not None

        for row in ndvi_series:
            test_db.refresh(row)
            assert row.ndvi_slope is not None
            assert float(row.ndvi_slope) == pytest.approx(slope, rel=1e-4)


# ─── 3. DivergenceService ─────────────────────────────────────────────────────


class TestDivergenceServiceAlertLevels:
    def test_alert_unknown_when_no_financial_and_no_satellite(
        self, test_db, sample_project
    ):
        """No data at all → alert_level = UNKNOWN."""
        service = DivergenceService(test_db)
        result = service.calculate_divergence(sample_project.project_uuid)
        assert result["alert_level"] == "UNKNOWN"
        assert result["divergence_score"] is None

    def test_alert_unknown_when_no_satellite_data(
        self, test_db, sample_project, financial_record
    ):
        """Financial data present but no satellite analyses → UNKNOWN."""
        service = DivergenceService(test_db)
        result = service.calculate_divergence(sample_project.project_uuid)
        assert result["alert_level"] == "UNKNOWN"
        assert result["financial_progress"] == pytest.approx(60.0, rel=0.01)
        assert result["physical_progress"] is None

    def test_alert_unknown_when_no_financial_data(
        self, test_db, sample_project, ndvi_series
    ):
        """Satellite data present but no financial records → UNKNOWN."""
        # Compute slope first to populate ndvi_slope on rows
        sat = SatelliteService(test_db)
        sat.compute_ndvi_slope(sample_project.project_uuid)

        service = DivergenceService(test_db)
        result = service.calculate_divergence(sample_project.project_uuid)
        assert result["alert_level"] == "UNKNOWN"

    def test_alert_red_when_high_divergence(
        self, test_db, sample_project, financial_record, ndvi_series
    ):
        """
        Financial absorption = 60 %, ndvi_slope is negative (physical progress ~65 %).
        Divergence = 60 - 65 = -5 → actually GREEN.

        Use a positive ndvi_slope + very high absorption to trigger RED.
        """
        # Override absorption rate to 90 % and set positive slope (no activity)
        financial_record.absorption_rate = Decimal("90.0")
        test_db.commit()

        # Manually set ndvi_slope = +0.08 (vegetation returning; physical_progress = 15)
        for row in ndvi_series:
            row.ndvi_slope = Decimal("0.08")
        test_db.commit()

        service = DivergenceService(test_db)
        result = service.calculate_divergence(sample_project.project_uuid)

        # divergence = 90 - 15 = 75 → RED
        assert result["alert_level"] == "RED"
        assert result["divergence_score"] > 50

    def test_alert_yellow_when_moderate_divergence(
        self, test_db, sample_project, financial_record, ndvi_series
    ):
        """
        Financial = 70 %, ndvi_slope near-zero (physical = 40 %).
        Divergence = 30 → YELLOW.
        """
        financial_record.absorption_rate = Decimal("70.0")
        test_db.commit()

        # ndvi_slope near zero → score = 40
        for row in ndvi_series:
            row.ndvi_slope = Decimal("0.005")
        test_db.commit()

        service = DivergenceService(test_db)
        result = service.calculate_divergence(sample_project.project_uuid)
        assert result["alert_level"] == "YELLOW"
        assert 20 <= result["divergence_score"] <= 50

    def test_alert_green_when_low_divergence(
        self, test_db, sample_project, financial_record, ndvi_series
    ):
        """
        Financial = 50 %, ndvi_slope strongly negative (physical = 90 %).
        Divergence = 50 - 90 = -40 → GREEN.
        """
        financial_record.absorption_rate = Decimal("50.0")
        test_db.commit()

        # Strong clearing activity
        for row in ndvi_series:
            row.ndvi_slope = Decimal("-0.08")
        test_db.commit()

        service = DivergenceService(test_db)
        result = service.calculate_divergence(sample_project.project_uuid)
        assert result["alert_level"] == "GREEN"

    def test_risk_level_updated_on_project(
        self, test_db, sample_project, financial_record, ndvi_series
    ):
        """RED alert should set project.risk_level = CRITICAL."""
        financial_record.absorption_rate = Decimal("90.0")
        for row in ndvi_series:
            row.ndvi_slope = Decimal("0.08")
        test_db.commit()

        service = DivergenceService(test_db)
        service.calculate_divergence(sample_project.project_uuid)

        test_db.refresh(sample_project)
        assert sample_project.risk_level == RiskLevel.CRITICAL

    def test_sar_delta_used_for_physical_progress(
        self, test_db, sample_project, financial_record, sar_analysis
    ):
        """sar_backscatter_delta = 4.2 → sar_score = 85 → physical = 85."""
        # financial = 60; physical = 85; divergence = -25 → GREEN
        service = DivergenceService(test_db)
        result = service.calculate_divergence(sample_project.project_uuid)
        assert result["physical_progress"] == pytest.approx(85.0, rel=0.01)
        assert result["alert_level"] == "GREEN"


class TestDivergenceServiceTimeline:
    def test_get_divergence_timeline_returns_correct_structure(
        self, test_db, sample_project, financial_record, ndvi_series
    ):
        """Timeline entries must contain required keys."""
        service = DivergenceService(test_db)
        timeline = service.get_divergence_timeline(sample_project.project_uuid)
        assert len(timeline) == 3
        required_keys = {
            "acquisition_date",
            "analysis_type",
            "ndvi_mean",
            "financial_progress",
        }
        for entry in timeline:
            assert required_keys.issubset(entry.keys())

    def test_get_divergence_timeline_empty_for_no_analyses(
        self, test_db, sample_project
    ):
        service = DivergenceService(test_db)
        timeline = service.get_divergence_timeline(sample_project.project_uuid)
        assert timeline == []


# ─── 4. Satellite router ──────────────────────────────────────────────────────


class TestSatelliteRouterQueueAnalysis:
    def test_queue_analysis_404_for_missing_project(self, client):
        fake_uuid = uuid.uuid4()
        resp = client.post(f"/api/v1/satellite/analyse/{fake_uuid}")
        assert resp.status_code == 404

    def test_queue_analysis_422_when_no_geolocation(
        self, client, sample_project, test_db
    ):
        """Project exists but no GeolocationRecord → 422."""
        resp = client.post(
            f"/api/v1/satellite/analyse/{sample_project.project_uuid}"
        )
        assert resp.status_code == 422

    def test_queue_analysis_returns_200_with_task_id(
        self, client, project_with_geolocation, test_db
    ):
        """With a valid project + geolocation, queue succeeds (mocked Celery)."""
        project, _geo = project_with_geolocation
        mock_result = MagicMock()
        mock_result.id = "celery-task-xyz"

        with patch("src.celery_app.celery_app") as mock_app:
            mock_app.send_task.return_value = mock_result
            resp = client.post(
                f"/api/v1/satellite/analyse/{project.project_uuid}"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["task_id"] == "celery-task-xyz"
        assert body["project_uuid"] == str(project.project_uuid)


class TestSatelliteRouterStatus:
    def test_get_task_status_returns_state(self, client):
        """Mock AsyncResult to verify status endpoint structure."""
        with patch(
            "celery.result.AsyncResult"
        ) as mock_async_result_cls:
            mock_ar = MagicMock()
            mock_ar.state = "PENDING"
            mock_ar.successful.return_value = False
            mock_ar.failed.return_value = False
            mock_async_result_cls.return_value = mock_ar

            resp = client.get("/api/v1/satellite/status/some-task-id")

        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == "some-task-id"
        assert body["status"] == "PENDING"


class TestSatelliteRouterDivergence:
    def test_get_divergence_404_missing_project(self, client):
        fake_uuid = uuid.uuid4()
        resp = client.get(f"/api/v1/projects/{fake_uuid}/divergence")
        assert resp.status_code == 404

    def test_get_divergence_returns_all_keys(
        self, client, sample_project, test_db
    ):
        """Divergence endpoint returns required keys (no satellite → UNKNOWN)."""
        resp = client.get(
            f"/api/v1/projects/{sample_project.project_uuid}/divergence"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "alert_level" in body
        assert "financial_progress" in body
        assert "physical_progress" in body
        assert "divergence_score" in body
        assert "timeline" in body
        assert body["alert_level"] == "UNKNOWN"


class TestSatelliteHeatMap:
    def test_heat_map_returns_feature_collection(self, client):
        """Empty DB → FeatureCollection with zero features."""
        resp = client.get("/api/v1/dashboard/heat-map")
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "FeatureCollection"
        assert isinstance(body["features"], list)
        assert "total" in body

    def test_heat_map_includes_geolocated_projects(
        self, client, project_with_geolocation, test_db
    ):
        """Projects with geolocation appear in the heat-map FeatureCollection."""
        project, _geo = project_with_geolocation
        resp = client.get("/api/v1/dashboard/heat-map")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        uuids = [f["properties"]["project_uuid"] for f in body["features"]]
        assert str(project.project_uuid) in uuids
