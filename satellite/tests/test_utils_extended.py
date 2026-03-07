"""Extended tests for satellite/src/utils.py — functions not covered by test_utils.py."""

import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pytest

_SAT_SRC = str(Path(__file__).parent.parent / "src")
if _SAT_SRC not in sys.path:
    sys.path.insert(0, _SAT_SRC)

from src.utils import (
    format_scene_id,
    create_output_filename,
    format_file_size,
    validate_date_range,
    list_safe_directories,
    clean_temp_files,
    ensure_directory,
    extract_statistics,
    create_bbox,
)


# =============================================================================
# format_scene_id
# =============================================================================


class TestFormatSceneId:

    def test_sentinel2_scene_id(self):
        sid = "S2A_MSIL2A_20240615T073611_N0510_R092_T37MCS_20240615T112233"
        result = format_scene_id(sid)
        assert result["satellite"] == "S2A"
        assert result["product_level"] == "MSIL2A"
        assert result["sensing_date"] == "20240615T073611"
        assert result["tile_id"] == "T37MCS"

    def test_sentinel1_scene_id(self):
        sid = "S1A_IW_GRDH_20240615T073611_12345"
        result = format_scene_id(sid)
        assert result["satellite"] == "S1A"
        assert result["mode"] == "IW"

    def test_unknown_scene_id(self):
        result = format_scene_id("RANDOM_SCENE_ID")
        assert result == {"raw_id": "RANDOM_SCENE_ID"}


# =============================================================================
# create_output_filename
# =============================================================================


class TestCreateOutputFilename:

    def test_standard_filename(self):
        dt = datetime(2024, 6, 15)
        name = create_output_filename("Sentinel-2", "NDVI", dt, "Kiambu")
        assert name == "Sentinel-2_NDVI_20240615_KIAMBU.tif"

    def test_custom_extension(self):
        dt = datetime(2024, 1, 1)
        name = create_output_filename("Sentinel-1", "SAR_VV", dt, "Nairobi", ".png")
        assert name == "Sentinel-1_SAR_VV_20240101_NAIROBI.png"

    def test_location_with_spaces(self):
        dt = datetime(2024, 3, 10)
        name = create_output_filename("Sentinel-2", "NDVI", dt, "Homa Bay")
        assert "HOMA_BAY" in name


# =============================================================================
# format_file_size
# =============================================================================


class TestFormatFileSize:

    def test_bytes(self):
        assert format_file_size(500) == "500.0 B"

    def test_kilobytes(self):
        assert format_file_size(1024) == "1.0 KB"

    def test_megabytes(self):
        assert format_file_size(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self):
        assert format_file_size(1024 ** 3) == "1.0 GB"

    def test_zero(self):
        assert format_file_size(0) == "0.0 B"


# =============================================================================
# validate_date_range
# =============================================================================


class TestValidateDateRange:

    def test_valid_range(self):
        start, end = validate_date_range("2024-01-01", "2024-12-31")
        assert start.year == 2024
        assert end.month == 12

    def test_same_date_valid(self):
        start, end = validate_date_range("2024-06-15", "2024-06-15")
        assert start == end

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError, match="must be after"):
            validate_date_range("2024-12-31", "2024-01-01")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            validate_date_range("2024/01/01", "2024-12-31")


# =============================================================================
# list_safe_directories
# =============================================================================


class TestListSafeDirectories:

    def test_finds_safe_dirs(self, tmp_path):
        (tmp_path / "S2A_test.SAFE").mkdir()
        (tmp_path / "S1A_test.SAFE").mkdir()
        (tmp_path / "not_safe").mkdir()
        (tmp_path / "file.txt").touch()

        result = list_safe_directories(tmp_path)
        assert len(result) == 2
        assert all(str(p).endswith(".SAFE") for p in result)

    def test_empty_directory(self, tmp_path):
        assert list_safe_directories(tmp_path) == []

    def test_nonexistent_directory(self, tmp_path):
        assert list_safe_directories(tmp_path / "nope") == []


# =============================================================================
# clean_temp_files
# =============================================================================


class TestCleanTempFiles:

    def test_removes_matching_files(self, tmp_path):
        (tmp_path / "a.tif.aux.xml").touch()
        (tmp_path / "b.tif.aux.xml").touch()
        (tmp_path / "keep.tif").touch()

        removed = clean_temp_files(tmp_path, "*.tif.aux.xml")
        assert removed == 2
        assert (tmp_path / "keep.tif").exists()

    def test_nonexistent_directory(self, tmp_path):
        assert clean_temp_files(tmp_path / "nope") == 0


# =============================================================================
# ensure_directory
# =============================================================================


class TestEnsureDirectory:

    def test_creates_nested_dirs(self, tmp_path):
        target = tmp_path / "a" / "b" / "c"
        result = ensure_directory(target)
        assert target.exists()
        assert result == target


# =============================================================================
# extract_statistics edge cases
# =============================================================================


class TestExtractStatisticsEdgeCases:

    def test_all_nan_returns_nan_stats(self):
        data = np.array([np.nan, np.nan, np.nan])
        stats = extract_statistics(data)
        assert np.isnan(stats["mean"])

    def test_with_inf_values_excluded(self):
        data = np.array([1.0, 2.0, np.inf, 3.0, -np.inf])
        stats = extract_statistics(data)
        assert stats["mean"] == pytest.approx(2.0)
        assert stats["min"] == 1.0
        assert stats["max"] == 3.0

    def test_with_mask(self):
        data = np.array([10, 20, 30, 40, 50], dtype=np.float32)
        mask = np.array([True, True, False, False, False])
        stats = extract_statistics(data, mask=mask)
        assert stats["mean"] == pytest.approx(15.0)


# =============================================================================
# create_bbox edge cases
# =============================================================================


class TestCreateBboxEdgeCases:

    def test_equator_symmetry(self):
        bbox = create_bbox(0.0, 36.0, radius_m=1000)
        min_lon, min_lat, max_lon, max_lat = bbox
        assert pytest.approx(max_lat - 0.0, abs=1e-4) == pytest.approx(0.0 - min_lat, abs=1e-4)

    def test_larger_radius_gives_larger_bbox(self):
        small = create_bbox(-1.0, 36.0, radius_m=100)
        large = create_bbox(-1.0, 36.0, radius_m=1000)
        assert (large[2] - large[0]) > (small[2] - small[0])  # wider
        assert (large[3] - large[1]) > (small[3] - small[1])  # taller
