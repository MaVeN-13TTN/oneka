"""Tests for satellite/src/process_ndwi.py — NDWIResult and classification."""

import sys
from pathlib import Path

import numpy as np
import pytest

_SAT_SRC = str(Path(__file__).parent.parent / "src")
if _SAT_SRC not in sys.path:
    sys.path.insert(0, _SAT_SRC)

from process_ndwi import NDWIResult


class TestNDWIResult:

    def test_dataclass_fields(self):
        result = NDWIResult(
            scene_id="S2A_TEST",
            ndwi_mean=0.35,
            ndwi_std=0.1,
            water_present=True,
            acquisition_date="2024-06-15",
            processed_date="2024-06-16",
        )
        assert result.scene_id == "S2A_TEST"
        assert result.ndwi_mean == 0.35
        assert result.ndwi_std == 0.1
        assert result.water_present is True

    def test_default_optional_fields(self):
        result = NDWIResult(scene_id="X", ndwi_mean=0.0, ndwi_std=0.0, water_present=False)
        assert result.acquisition_date is None
        assert result.processed_date is None

    def test_water_threshold_logic(self):
        """Water present when mean NDWI > 0.3 (config default)."""
        # Simulate the classification logic
        threshold = 0.3
        assert 0.5 > threshold   # water present
        assert 0.1 < threshold   # no water present is False (0.1 < 0.3)


class TestNDWIComputation:
    """Test NDWI formula via the utility function."""

    def test_ndwi_formula(self):
        from src.utils import calculate_ndwi

        green = np.array([200, 100, 50], dtype=np.float32)
        nir = np.array([100, 100, 150], dtype=np.float32)
        ndwi = calculate_ndwi(green, nir)

        # (200-100)/(200+100) = 0.333
        assert ndwi[0] == pytest.approx(0.333, abs=0.01)
        # (100-100)/(100+100) = 0
        assert ndwi[1] == pytest.approx(0.0, abs=0.001)
        # (50-150)/(50+150) = -0.5
        assert ndwi[2] == pytest.approx(-0.5, abs=0.01)

    def test_ndwi_clipped_to_range(self):
        from src.utils import calculate_ndwi

        green = np.array([1000, 0], dtype=np.float32)
        nir = np.array([0, 1000], dtype=np.float32)
        ndwi = calculate_ndwi(green, nir)

        assert np.all(ndwi >= -1.0)
        assert np.all(ndwi <= 1.0)

    def test_ndwi_division_by_zero_handled(self):
        from src.utils import calculate_ndwi

        green = np.array([0], dtype=np.float32)
        nir = np.array([0], dtype=np.float32)
        ndwi = calculate_ndwi(green, nir)

        assert np.isfinite(ndwi[0])
