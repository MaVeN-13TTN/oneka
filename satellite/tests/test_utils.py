"""
Unit tests for utility functions.
"""

import pytest
import numpy as np
from src.utils import (
    parse_coordinates,
    create_bbox,
    calculate_ndvi,
    calculate_ndwi,
    extract_statistics,
)


def test_parse_coordinates_valid():
    """Test valid coordinate parsing."""
    lat, lon = parse_coordinates(-1.2921, 36.8219)
    assert lat == -1.2921
    assert lon == 36.8219


def test_parse_coordinates_invalid_lat():
    """Test invalid latitude."""
    with pytest.raises(ValueError):
        parse_coordinates(91.0, 36.8219)


def test_parse_coordinates_invalid_lon():
    """Test invalid longitude."""
    with pytest.raises(ValueError):
        parse_coordinates(-1.2921, 181.0)


def test_create_bbox():
    """Test bounding box creation."""
    lat, lon = -1.2921, 36.8219
    bbox = create_bbox(lat, lon, radius_m=500)

    min_lon, min_lat, max_lon, max_lat = bbox

    assert min_lon < lon < max_lon
    assert min_lat < lat < max_lat


def test_calculate_ndvi():
    """Test NDVI calculation."""
    nir = np.array([[100, 150], [200, 250]], dtype=np.float32)
    red = np.array([[50, 75], [100, 125]], dtype=np.float32)

    ndvi = calculate_ndvi(nir, red)

    # NDVI should be between -1 and 1
    assert np.all(ndvi >= -1.0)
    assert np.all(ndvi <= 1.0)

    # NDVI for these values should be positive
    assert np.all(ndvi > 0)


def test_calculate_ndwi():
    """Test NDWI calculation."""
    green = np.array([[100, 150], [200, 250]], dtype=np.float32)
    nir = np.array([[50, 75], [100, 125]], dtype=np.float32)

    ndwi = calculate_ndwi(green, nir)

    # NDWI should be between -1 and 1
    assert np.all(ndwi >= -1.0)
    assert np.all(ndwi <= 1.0)


def test_extract_statistics():
    """Test statistics extraction."""
    data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=np.float32)

    stats = extract_statistics(data)

    assert stats["mean"] == 5.5
    assert stats["min"] == 1.0
    assert stats["max"] == 10.0
    assert stats["median"] == 5.5


def test_extract_statistics_with_nan():
    """Test statistics with NaN values."""
    data = np.array([1, 2, np.nan, 4, 5, np.nan, 7, 8, 9, 10], dtype=np.float32)

    stats = extract_statistics(data)

    # Should ignore NaN values
    assert not np.isnan(stats["mean"])
    assert stats["mean"] == pytest.approx(5.75, rel=1e-2)
