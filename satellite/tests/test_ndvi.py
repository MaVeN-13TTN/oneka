"""Tests for compute_ndvi_slope from satellite/src/process_ndvi.py."""

import sys
from pathlib import Path

import numpy as np
import pytest

_SAT_SRC = str(Path(__file__).parent.parent / "src")
if _SAT_SRC not in sys.path:
    sys.path.insert(0, _SAT_SRC)

from process_ndvi import compute_ndvi_slope


class TestComputeNDVISlope:

    def test_declining_ndvi_gives_negative_slope(self):
        dates = ["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01"]
        means = [0.6, 0.5, 0.3, 0.1]
        slope = compute_ndvi_slope(dates, means)
        assert slope is not None
        assert slope < 0

    def test_increasing_ndvi_gives_positive_slope(self):
        dates = ["2024-01-01", "2024-04-01", "2024-07-01"]
        means = [0.1, 0.3, 0.5]
        slope = compute_ndvi_slope(dates, means)
        assert slope is not None
        assert slope > 0

    def test_constant_ndvi_gives_zero_slope(self):
        dates = ["2024-01-01", "2024-06-01", "2024-12-01"]
        means = [0.4, 0.4, 0.4]
        slope = compute_ndvi_slope(dates, means)
        assert slope is not None
        assert abs(slope) < 0.001

    def test_too_few_dates_returns_none(self):
        assert compute_ndvi_slope(["2024-01-01"], [0.5]) is None
        assert compute_ndvi_slope([], []) is None

    def test_nan_values_excluded(self):
        dates = ["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01"]
        means = [0.6, float("nan"), 0.4, 0.2]
        slope = compute_ndvi_slope(dates, means)
        assert slope is not None
        assert slope < 0  # still declining

    def test_all_nan_returns_none(self):
        dates = ["2024-01-01", "2024-04-01"]
        means = [float("nan"), float("nan")]
        slope = compute_ndvi_slope(dates, means)
        assert slope is None

    def test_two_points_gives_valid_slope(self):
        dates = ["2024-01-01", "2025-01-01"]
        means = [0.6, 0.3]
        slope = compute_ndvi_slope(dates, means)
        assert slope is not None
        # ~-0.025 NDVI/month over 12 months
        assert -0.04 < slope < -0.01
