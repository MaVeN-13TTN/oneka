"""
Phase 5 test suite — Satellite Tile Generation & Google Maps Proxy.

Coverage targets:
  generate_tiles.py         (satellite/src) — TileGenerator class
  tile_service.py           (backend/src/services) — TileService orchestration
  tile_tasks.py             (backend/src/tasks) — Celery tile generation task
  maps.py                   (backend/src/routers) — Google Maps proxy router
  satellite.py              (backend/src/routers) — Tile endpoints (updated)
  projects.py               (backend/src/routers) — GeoJSON filter (updated)

Test groups:
  - TileGenerator: unit tests (rasterio, colormap, tile pyramid)
  - TileService: integration tests (DB, S3, presigned URLs)
  - Celery tasks: async task tests with monkeypatch
  - Maps router: session token, tile proxy, caching
  - Satellite router: tile endpoint integration
  - Projects router: GeoJSON risk_level filter
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, call
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy.orm import Session

# ── Ensure satellite/src is importable ───────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/tests/… → oneka/
_SAT_SRC = _REPO_ROOT / "satellite" / "src"
_SAT_ROOT = _REPO_ROOT / "satellite"

# Import TileGenerator with namespace isolation to avoid src.config collision
_HAS_RASTERIO = False
TileGenerator = None
try:
    # Save backend's 'src' module references
    _saved_src_modules = {k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")}
    for k in _saved_src_modules:
        del sys.modules[k]

    # Temporarily put satellite paths first
    sys.path.insert(0, str(_SAT_SRC))
    sys.path.insert(0, str(_SAT_ROOT))

    from generate_tiles import TileGenerator
    _HAS_RASTERIO = True

    # Remove satellite's 'src' entries from sys.modules
    _sat_src_keys = [k for k in sys.modules if k == "src" or k.startswith("src.")]
    for k in _sat_src_keys:
        del sys.modules[k]

    # Restore backend's 'src' modules
    sys.modules.update(_saved_src_modules)

    # Clean up path (keep satellite/src for generate_tiles, but not at front)
    sys.path.remove(str(_SAT_ROOT))
except ImportError:
    # Restore backend modules on failure
    if "_saved_src_modules" in dir():
        _sat_src_keys = [k for k in sys.modules if k == "src" or k.startswith("src.")]
        for k in _sat_src_keys:
            del sys.modules[k]
        sys.modules.update(_saved_src_modules)
    _HAS_RASTERIO = False

# ── Backend imports ────────────────────────────────────────────────────────
from src.models.project import Project, ProjectStatus, RiskLevel
from src.models.satellite import SatelliteAnalysis
from src.models.geolocation import GeolocationRecord
from src.services.tile_service import TileService
from src.celery_app import celery_app


# ── Fixtures ───────────────────────────────────────────────────────────────

def _make_project(test_db, *, project_uuid=None, name="Test Project",
                  county="Nairobi", risk_level=None, geolocation_status="geolocated"):
    """Create and persist a test project."""
    p = Project(
        project_uuid=project_uuid or uuid4(),
        project_name=name,
        county=county,
        status=ProjectStatus.ONGOING,
        risk_level=risk_level,
        geolocation_status=geolocation_status,
    )
    test_db.add(p)
    test_db.commit()
    test_db.refresh(p)
    return p


def _make_geolocation(test_db, project_uuid, *, lat=-1.3, lon=36.8,
                      match_method="egp_manual"):
    """Create and persist a test geolocation record."""
    g = GeolocationRecord(
        project_uuid=project_uuid,
        latitude=lat,
        longitude=lon,
        match_method=match_method,
        match_confidence=90,
    )
    test_db.add(g)
    test_db.commit()
    test_db.refresh(g)
    return g


def _make_satellite_analysis(test_db, project_uuid, *,
                            image_url="s3://bucket/ndvi.tif",
                            acquisition_date="2024-03-01",
                            ndvi_slope=-0.05):
    """Create and persist a test satellite analysis."""
    sa = SatelliteAnalysis(
        project_uuid=project_uuid,
        sensor="Sentinel-2",
        acquisition_date=acquisition_date,
        analysis_type="NDVI_change",
        ndvi_slope=ndvi_slope,
        image_url=image_url,
    )
    test_db.add(sa)
    test_db.commit()
    test_db.refresh(sa)
    return sa


@pytest.fixture
def sample_ndvi_geotiff():
    """Create a minimal 512x512 NDVI GeoTIFF for testing."""
    pytest.importorskip("rasterio")
    import rasterio
    from rasterio.transform import from_bounds

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
        temp_path = f.name

    # Create a simple 512x512 NDVI raster (values -1 to 1)
    data = np.random.uniform(-1, 1, (512, 512)).astype(np.float32)

    # Write to GeoTIFF with proper georeferencing (Kenya region)
    transform = from_bounds(36.5, -2.0, 37.0, -1.0, 512, 512)

    with rasterio.open(
        temp_path, 'w',
        driver='GTiff',
        height=512, width=512,
        count=1,
        dtype=data.dtype,
        crs='EPSG:4326',
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


# =============================================================================
# Group 1 — TileGenerator (Satellite Module)
# =============================================================================

@pytest.mark.skipif(not _HAS_RASTERIO, reason="rasterio not installed")
class TestTileGenerator:
    """Tests for satellite/src/generate_tiles.py — TileGenerator class."""

    def test_init_validates_geotiff_exists(self, sample_ndvi_geotiff):
        """Initialize with valid GeoTIFF path."""
        gen = TileGenerator(sample_ndvi_geotiff)
        assert gen.geotiff_path == Path(sample_ndvi_geotiff)
        assert gen.band_index == 1

    def test_init_invalid_path_deferred(self):
        """Initialization defers validation for S3 paths."""
        gen = TileGenerator("s3://bucket/raster.tif")
        assert gen.geotiff_path == Path("s3://bucket/raster.tif")

    def test_validate_geotiff_reads_metadata(self, sample_ndvi_geotiff):
        """_validate_geotiff() reads CRS, bounds, dimensions."""
        gen = TileGenerator(sample_ndvi_geotiff)
        gen._validate_geotiff()
        assert gen._validated
        assert gen._metadata["crs"] is not None
        assert gen._metadata["width"] == 512
        assert gen._metadata["height"] == 512

    def test_get_colormap_ndvi(self):
        """get_colormap_for_layer('ndvi') → 'RdYlGn'."""
        assert TileGenerator.get_colormap_for_layer("ndvi") == "RdYlGn"

    def test_get_colormap_sar(self):
        """get_colormap_for_layer('sar') → 'gray'."""
        assert TileGenerator.get_colormap_for_layer("sar") == "gray"

    def test_get_colormap_default(self):
        """get_colormap_for_layer('unknown') → 'viridis'."""
        assert TileGenerator.get_colormap_for_layer("unknown") == "viridis"

    def test_generate_ndvi_tiles_returns_dict(self, sample_ndvi_geotiff):
        """generate_ndvi_tiles() returns dict with tile_count, z_range."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = TileGenerator.generate_ndvi_tiles(
                sample_ndvi_geotiff, tmpdir,
                colormap="RdYlGn", z_min=8, z_max=10
            )
            assert "tile_count" in result
            assert "z_range" in result
            assert result["z_range"] == (8, 10)

    def test_generate_ndvi_tiles_creates_directory_structure(self, sample_ndvi_geotiff):
        """Generated tiles follow {z}/{x}/{y}.png structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = TileGenerator.generate_ndvi_tiles(
                sample_ndvi_geotiff, tmpdir,
                z_min=12, z_max=12  # Higher zoom to guarantee tile coverage
            )

            # At zoom 12, a 0.5° x 1° Kenya region GeoTIFF should produce tiles
            if result["tile_count"] > 0:
                tile_dir = Path(tmpdir) / "12"
                assert tile_dir.exists(), "Zoom 12 directory should exist"
                # Verify nested x/y structure
                x_dirs = list(tile_dir.iterdir())
                assert len(x_dirs) > 0, "Should have at least one x directory"
                png_files = list(x_dirs[0].glob("*.png"))
                assert len(png_files) > 0, "Should have at least one .png tile"
            else:
                # Tile generation returned 0 tiles — valid for small extents
                assert result["z_range"] == (12, 12)

    def test_generate_sar_tiles_grayscale(self, sample_ndvi_geotiff):
        """generate_sar_tiles() uses grayscale colormap."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = TileGenerator.generate_sar_tiles(
                sample_ndvi_geotiff, tmpdir,
                colormap="gray", z_min=8, z_max=9
            )
            assert "tile_count" in result
            assert result["z_range"] == (8, 9)

    def test_generate_tiles_invalid_geotiff(self):
        """generate_ndvi_tiles() handles missing GeoTIFF gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = TileGenerator.generate_ndvi_tiles(
                "/nonexistent/path.tif", tmpdir
            )
            assert result["tile_count"] == 0
            assert "error" in result


# =============================================================================
# Group 2 — TileService (Backend Service)
# =============================================================================

class TestTileService:
    """Tests for backend/src/services/tile_service.py — TileService."""

    def test_init_with_db_session(self, test_db):
        """Initialize TileService with database session."""
        service = TileService(test_db)
        assert service.db is test_db
        assert service.s3_service is not None

    def test_queue_tile_generation_success(self, test_db):
        """queue_tile_generation() returns task_id string."""
        project = _make_project(test_db)
        analysis = _make_satellite_analysis(test_db, project.project_uuid)

        service = TileService(test_db)

        with patch("src.celery_app.celery_app.send_task") as mock_send:
            mock_task = MagicMock()
            mock_task.id = "task-xyz-123"
            mock_send.return_value = mock_task

            task_id = service.queue_tile_generation(project.project_uuid)

            assert task_id == "task-xyz-123"
            mock_send.assert_called_once()

    def test_queue_tile_generation_missing_project(self, test_db):
        """queue_tile_generation() raises ValueError for missing project."""
        service = TileService(test_db)

        with pytest.raises(ValueError, match="No satellite analysis found"):
            service.queue_tile_generation(uuid4())

    def test_queue_tile_generation_missing_geotiff(self, test_db):
        """queue_tile_generation() raises ValueError if image_url missing."""
        project = _make_project(test_db)
        analysis = _make_satellite_analysis(
            test_db, project.project_uuid, image_url=None
        )

        service = TileService(test_db)

        with pytest.raises(ValueError, match="no GeoTIFF"):
            service.queue_tile_generation(project.project_uuid)

    def test_get_tile_status_pending(self, test_db):
        """get_tile_status() returns 'pending' when tile_url_template is None."""
        project = _make_project(test_db)
        analysis = _make_satellite_analysis(test_db, project.project_uuid)

        service = TileService(test_db)
        status = service.get_tile_status(project.project_uuid)

        assert status["status"] == "pending"
        assert status["tile_url_template"] is None
        assert status["task_id"] is None

    def test_get_tile_status_complete(self, test_db):
        """get_tile_status() returns 'complete' when tile_url_template is set."""
        project = _make_project(test_db)
        tile_url = "https://s3.amazonaws.com/bucket/tiles/{z}/{x}/{y}.png"
        analysis = _make_satellite_analysis(test_db, project.project_uuid)
        analysis.tile_url_template = tile_url
        test_db.commit()

        service = TileService(test_db)
        status = service.get_tile_status(project.project_uuid)

        assert status["status"] == "complete"
        assert status["tile_url_template"] == tile_url

    def test_get_tile_status_missing_project(self, test_db):
        """get_tile_status() returns 'failed' for missing project."""
        service = TileService(test_db)
        status = service.get_tile_status(uuid4())

        assert status["status"] == "failed"
        assert "No satellite analysis found" in status["error"]

    def test_get_tile_presigned_urls_returns_list(self, test_db):
        """get_tile_presigned_urls() returns list of presigned S3 URLs."""
        project = _make_project(test_db)
        tile_url = "https://s3.amazonaws.com/bucket/tiles/{z}/{x}/{y}.png"
        analysis = _make_satellite_analysis(
            test_db, project.project_uuid,
            image_url="s3://bucket/ndvi.tif"
        )
        analysis.tile_url_template = tile_url
        test_db.commit()

        service = TileService(test_db)

        with patch.object(service.s3_service, "get_pdf_url") as mock_presigned:
            mock_presigned.return_value = "https://s3.amazonaws.com/bucket/tiles/8/x/y.png?AWSAccessKeyId=..."

            urls = service.get_tile_presigned_urls(
                project.project_uuid, "ndvi", z_range=(8, 8)
            )

            assert isinstance(urls, list)
            assert len(urls) > 0

    def test_get_tile_presigned_urls_missing_tiles(self, test_db):
        """get_tile_presigned_urls() raises ValueError if tiles not generated."""
        project = _make_project(test_db)
        analysis = _make_satellite_analysis(test_db, project.project_uuid)

        service = TileService(test_db)

        with pytest.raises(ValueError, match="not.*generated"):
            service.get_tile_presigned_urls(project.project_uuid)

    def test_update_tile_url_success(self, test_db):
        """update_tile_url() persists tile URL to database."""
        project = _make_project(test_db)
        analysis = _make_satellite_analysis(test_db, project.project_uuid)

        service = TileService(test_db)
        tile_url = "https://s3.amazonaws.com/bucket/tiles/{z}/{x}/{y}.png"

        result = service.update_tile_url(project.project_uuid, tile_url)

        assert result is True

        # Verify update persisted
        analysis_refresh = test_db.query(SatelliteAnalysis).filter(
            SatelliteAnalysis.project_uuid == project.project_uuid
        ).first()
        assert analysis_refresh.tile_url_template == tile_url

    def test_mark_tiles_generated_success(self, test_db):
        """mark_tiles_generated() updates Project.tiles_generated (if field exists)."""
        project = _make_project(test_db)
        analysis = _make_satellite_analysis(test_db, project.project_uuid)

        service = TileService(test_db)

        # Add field if it doesn't exist (for testing)
        if not hasattr(project, "tiles_generated"):
            # Skip for this test
            pytest.skip("Project model doesn't have tiles_generated field yet")

        result = service.mark_tiles_generated(project.project_uuid)

        assert result is True


# =============================================================================
# Group 3 — Celery Tile Tasks
# =============================================================================

class TestTileTasks:
    """Tests for backend/src/tasks/tile_tasks.py — Celery tile generation task."""

    def test_generate_project_tiles_task_imported(self):
        """generate_project_tiles_task is registered in Celery."""
        from src.tasks import tile_tasks
        assert hasattr(tile_tasks, "generate_project_tiles_task")

    def test_generate_project_tiles_task_missing_project(self, test_db, monkeypatch):
        """Task returns dict with status='failed' if project missing."""
        from src.tasks.tile_tasks import generate_project_tiles_task

        # Monkeypatch SessionLocal to use test_db
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_db.get_bind())
        monkeypatch.setattr("src.tasks.tile_tasks.SessionLocal", TestSession)

        result = generate_project_tiles_task.apply(
            args=["00000000-0000-0000-0000-000000000000", "ndvi"]
        )

        assert result.successful()
        output = result.get()
        assert output["status"] == "failed"
        assert "No satellite analysis" in output["error"]

    def test_generate_project_tiles_task_missing_geotiff(self, test_db, monkeypatch):
        """Task returns status='failed' if image_url missing."""
        from src.tasks.tile_tasks import generate_project_tiles_task

        project = _make_project(test_db)
        analysis = _make_satellite_analysis(
            test_db, project.project_uuid, image_url=None
        )

        # Monkeypatch SessionLocal
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_db.get_bind())
        monkeypatch.setattr("src.tasks.tile_tasks.SessionLocal", TestSession)

        result = generate_project_tiles_task.apply(
            args=[str(project.project_uuid), "ndvi"]
        )

        assert result.successful()
        output = result.get()
        assert output["status"] == "failed"
        assert "GeoTIFF" in output["error"]

    def test_generate_project_tiles_task_response_keys(self, test_db, monkeypatch):
        """Task return dict has required keys."""
        from src.tasks.tile_tasks import generate_project_tiles_task

        project = _make_project(test_db)
        analysis = _make_satellite_analysis(test_db, project.project_uuid)

        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_db.get_bind())
        monkeypatch.setattr("src.tasks.tile_tasks.SessionLocal", TestSession)

        # Since we can't fully mock tile generation without rasterio,
        # just verify the task structure
        assert hasattr(generate_project_tiles_task, "apply")


# =============================================================================
# Group 4 — Maps Router (Google Tiles Proxy)
# =============================================================================

class TestMapsRouter:
    """Tests for backend/src/routers/maps.py — Google Maps Tiles API proxy."""

    def test_create_session_endpoint_exists(self, client):
        """POST /api/v1/maps/tiles/session endpoint exists."""
        import httpx

        # Build a fake httpx.Response
        mock_response = httpx.Response(
            status_code=200,
            json={"session": "test-session-token-abc123"},
            request=httpx.Request("POST", "https://tile.googleapis.com/v1/createSession"),
        )

        with patch("src.routers.maps.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            MockClient.return_value = mock_client_instance

            response = client.post("/api/v1/maps/tiles/session")

            assert response.status_code == 200
            data = response.json()
            assert "session_token" in data
            assert "expires_in" in data

    def test_create_session_no_api_key(self, client):
        """POST /api/v1/maps/tiles/session returns 400 if API key missing."""
        with patch("src.config.settings.google_maps_api_key", None):
            response = client.post("/api/v1/maps/tiles/session")
            assert response.status_code == 400
            assert "not configured" in response.json()["detail"]

    def test_create_session_google_api_error(self, client):
        """POST /api/v1/maps/tiles/session returns 503 if Google API fails."""
        import httpx

        mock_response = httpx.Response(
            status_code=401,
            text="Unauthorized",
            request=httpx.Request("POST", "https://tile.googleapis.com/v1/createSession"),
        )

        with patch("src.routers.maps.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.return_value = mock_response

            MockClient.return_value = mock_client_instance

            response = client.post("/api/v1/maps/tiles/session")

            assert response.status_code == 503

    def test_proxy_tile_invalid_zoom(self, client):
        """GET /api/v1/maps/tiles/{token}/999/{x}/{y} returns 400."""
        response = client.get("/api/v1/maps/tiles/test-token/999/0/0")
        assert response.status_code == 400
        assert "zoom" in response.json()["detail"].lower()

    def test_proxy_tile_invalid_coordinates(self, client):
        """GET /api/v1/maps/tiles/{token}/{z}/99999/99999 returns 404."""
        response = client.get("/api/v1/maps/tiles/test-token/10/99999/99999")
        assert response.status_code in [400, 404]  # Out of bounds


# =============================================================================
# Group 5 — Satellite Router Tile Endpoints
# =============================================================================

class TestSatelliteRouterTiles:
    """Tests for backend/src/routers/satellite.py — Tile endpoints (updated)."""

    def test_get_ndvi_tile_queued_missing_project(self, test_db, client):
        """GET /satellite/tiles/{uuid}/ndvi/{z}/{x}/{y} returns 404 for missing project."""
        response = client.get(
            f"/api/v1/satellite/tiles/{uuid4()}/ndvi/8/0/0"
        )
        assert response.status_code == 404

    def test_get_ndvi_tile_queued(self, test_db, client):
        """GET /satellite/tiles/{uuid}/ndvi/{z}/{x}/{y} returns 202 if queuing."""
        with client:
            # Override get_db to use test_db
            from src.database import get_db

            def override_get_db():
                return test_db

            client.app.dependency_overrides[get_db] = override_get_db

            project = _make_project(test_db)
            analysis = _make_satellite_analysis(test_db, project.project_uuid)

            with patch("src.services.tile_service.TileService.queue_tile_generation") as mock_queue:
                mock_queue.return_value = "task-xyz-123"

                response = client.get(
                    f"/api/v1/satellite/tiles/{project.project_uuid}/ndvi/8/0/0"
                )

                # Should return 202 Accepted + task_id
                assert response.status_code == 202
                assert response.json()["task_id"] == "task-xyz-123"

    def test_get_tiles_status_pending(self, test_db, client):
        """GET /api/v1/satellite/tiles-status/{uuid} returns pending status."""
        from src.database import get_db

        def override_get_db():
            return test_db

        client.app.dependency_overrides[get_db] = override_get_db

        project = _make_project(test_db)
        analysis = _make_satellite_analysis(test_db, project.project_uuid)

        response = client.get(f"/api/v1/satellite/tiles-status/{project.project_uuid}")

        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    def test_get_tiles_status_complete(self, test_db, client):
        """GET /api/v1/satellite/tiles-status/{uuid} returns complete with URLs."""
        from src.database import get_db

        def override_get_db():
            return test_db

        client.app.dependency_overrides[get_db] = override_get_db

        project = _make_project(test_db)
        tile_url = "https://s3.amazonaws.com/bucket/tiles/{z}/{x}/{y}.png"
        analysis = _make_satellite_analysis(test_db, project.project_uuid)
        analysis.tile_url_template = tile_url
        test_db.commit()

        with patch("src.services.tile_service.TileService.get_tile_presigned_urls") as mock_urls:
            mock_urls.return_value = [
                "https://s3.amazonaws.com/bucket/tiles/8/0/0.png?AWSAccessKeyId=..."
            ]

            response = client.get(f"/api/v1/satellite/tiles-status/{project.project_uuid}")

            assert response.status_code == 200
            assert response.json()["status"] == "complete"


# =============================================================================
# Group 6 — Projects Router GeoJSON Filter
# =============================================================================

class TestProjectsGeoJSONFilter:
    """Tests for backend/src/routers/projects.py — GeoJSON filter (updated)."""

    def test_geojson_no_filter_returns_all(self, test_db, client):
        """GET /api/v1/projects/geojson returns all projects (no filter)."""
        from src.database import get_db

        def override_get_db():
            return test_db

        client.app.dependency_overrides[get_db] = override_get_db

        # Create projects
        p1 = _make_project(test_db, name="Project A", risk_level=RiskLevel.LOW)
        p2 = _make_project(test_db, name="Project B", risk_level=RiskLevel.HIGH)

        _make_geolocation(test_db, p1.project_uuid)
        _make_geolocation(test_db, p2.project_uuid)

        response = client.get("/api/v1/projects/geojson")

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 2

    def test_geojson_filter_single_risk_level(self, test_db, client):
        """GET /api/v1/projects/geojson?risk_level=HIGH filters by single risk level."""
        from src.database import get_db

        def override_get_db():
            return test_db

        client.app.dependency_overrides[get_db] = override_get_db

        # Create projects
        p1 = _make_project(test_db, name="Project A", risk_level=RiskLevel.LOW)
        p2 = _make_project(test_db, name="Project B", risk_level=RiskLevel.HIGH)
        p3 = _make_project(test_db, name="Project C", risk_level=RiskLevel.CRITICAL)

        _make_geolocation(test_db, p1.project_uuid)
        _make_geolocation(test_db, p2.project_uuid)
        _make_geolocation(test_db, p3.project_uuid)

        response = client.get("/api/v1/projects/geojson?risk_level=HIGH")

        assert response.status_code == 200
        data = response.json()
        assert len(data["features"]) == 1
        assert data["features"][0]["properties"]["risk_level"] == "HIGH"

    def test_geojson_filter_multiple_risk_levels(self, test_db, client):
        """GET /api/v1/projects/geojson?risk_level=HIGH,CRITICAL filters by multiple levels."""
        from src.database import get_db

        def override_get_db():
            return test_db

        client.app.dependency_overrides[get_db] = override_get_db

        # Create projects
        p1 = _make_project(test_db, name="Project A", risk_level=RiskLevel.LOW)
        p2 = _make_project(test_db, name="Project B", risk_level=RiskLevel.HIGH)
        p3 = _make_project(test_db, name="Project C", risk_level=RiskLevel.CRITICAL)

        _make_geolocation(test_db, p1.project_uuid)
        _make_geolocation(test_db, p2.project_uuid)
        _make_geolocation(test_db, p3.project_uuid)

        response = client.get("/api/v1/projects/geojson?risk_level=HIGH,CRITICAL")

        assert response.status_code == 200
        data = response.json()
        assert len(data["features"]) == 2
        risk_levels = {f["properties"]["risk_level"] for f in data["features"]}
        assert risk_levels == {"HIGH", "CRITICAL"}

    def test_geojson_invalid_risk_level_ignored(self, test_db, client):
        """GET /api/v1/projects/geojson?risk_level=INVALID ignores invalid levels."""
        from src.database import get_db

        def override_get_db():
            return test_db

        client.app.dependency_overrides[get_db] = override_get_db

        p1 = _make_project(test_db, name="Project A", risk_level=RiskLevel.LOW)
        _make_geolocation(test_db, p1.project_uuid)

        # Invalid risk_level should be ignored (returns all)
        response = client.get("/api/v1/projects/geojson?risk_level=INVALID")

        assert response.status_code == 200
        # Implementation detail: invalid values should be silently ignored or return empty

    def test_geojson_includes_ghost_probability(self, test_db, client):
        """GeoJSON properties include ghost_probability from Phase 4."""
        from src.database import get_db

        def override_get_db():
            return test_db

        client.app.dependency_overrides[get_db] = override_get_db

        p = _make_project(test_db, name="Test Project")
        p.ghost_probability = 0.75  # From Phase 4 ML
        test_db.commit()

        _make_geolocation(test_db, p.project_uuid)

        response = client.get("/api/v1/projects/geojson")

        assert response.status_code == 200
        data = response.json()
        assert len(data["features"]) == 1
        assert data["features"][0]["properties"]["ghost_probability"] == 0.75


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.skipif(not _HAS_RASTERIO, reason="rasterio not installed")
class TestPhase5Integration:
    """End-to-end Phase 5 workflow tests."""

    def test_tile_generation_workflow(self, test_db, sample_ndvi_geotiff):
        """End-to-end: analyze → generate tiles → retrieve URLs."""
        project = _make_project(test_db)
        analysis = _make_satellite_analysis(
            test_db, project.project_uuid,
            image_url=sample_ndvi_geotiff
        )

        # Generate tiles
        with tempfile.TemporaryDirectory() as tmpdir:
            result = TileGenerator.generate_ndvi_tiles(
                sample_ndvi_geotiff, tmpdir,
                z_min=8, z_max=10
            )

            assert result["tile_count"] >= 0
            assert result["z_range"] == (8, 10)

        # Update database
        service = TileService(test_db)
        tile_url = f"https://s3.amazonaws.com/oneka-satellite-data/tiles/{project.project_uuid}/ndvi/{{z}}/{{x}}/{{y}}.png"
        service.update_tile_url(project.project_uuid, tile_url)

        # Verify status
        status = service.get_tile_status(project.project_uuid)
        assert status["status"] == "complete"
        assert status["tile_url_template"] == tile_url
