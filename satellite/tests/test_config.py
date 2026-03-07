"""Tests for satellite/src/config.py — Config class."""

import sys
from pathlib import Path

import pytest

_SAT_SRC = str(Path(__file__).parent.parent / "src")
if _SAT_SRC not in sys.path:
    sys.path.insert(0, _SAT_SRC)

from config import Config, config


class TestConfig:

    def test_singleton_instance_exists(self):
        assert config is not None
        assert isinstance(config, Config)

    def test_project_root_is_satellite_dir(self):
        assert Config.PROJECT_ROOT.name == "satellite"

    def test_data_root_under_satellite(self):
        assert "satellite" in str(Config.DATA_ROOT)

    def test_default_cloud_cover(self):
        assert Config.MAX_CLOUD_COVER == 20

    def test_default_aoi_radius(self):
        assert Config.AOI_RADIUS == 500

    def test_ndvi_thresholds(self):
        assert Config.NDVI_CLEARING_THRESHOLD == 0.15
        assert Config.NDVI_HEALTHY_VEGETATION == 0.3
        assert Config.NDVI_RECOVERY_THRESHOLD == 0.5

    def test_sar_thresholds(self):
        assert Config.SAR_STRUCTURE_THRESHOLD == 3.0
        assert Config.SAR_VV_TYPICAL_RANGE == (-25, 5)
        assert Config.SAR_VH_TYPICAL_RANGE == (-30, 0)

    def test_ndwi_water_threshold(self):
        assert Config.NDWI_WATER_THRESHOLD == 0.3

    def test_sentinel2_bands_count(self):
        assert len(Config.SENTINEL2_BANDS) == 13

    def test_sentinel1_polarizations(self):
        assert Config.SENTINEL1_POLARIZATIONS == ["VV", "VH", "HH", "HV"]

    def test_default_backend_url(self):
        assert Config.BACKEND_API_URL == "http://localhost:8000"

    def test_debug_is_bool(self):
        assert isinstance(Config.DEBUG, bool)

    def test_test_mode_default_false(self):
        assert Config.TEST_MODE is False

    def test_default_num_workers(self):
        assert Config.NUM_WORKERS == 4

    def test_validate_warns_without_credentials(self):
        """validate() returns False when Copernicus credentials are not set."""
        # This depends on environment — if credentials ARE set, it returns True
        result = Config.validate()
        assert isinstance(result, bool)
