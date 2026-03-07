"""Tests for satellite/src/generate_tiles.py — static helper methods."""

import sys
from pathlib import Path

import numpy as np
import pytest

_SAT_SRC = str(Path(__file__).parent.parent / "src")
if _SAT_SRC not in sys.path:
    sys.path.insert(0, _SAT_SRC)

from generate_tiles import TileGenerator


class TestGetColormapForLayer:

    def test_ndvi_colormap(self):
        assert TileGenerator.get_colormap_for_layer("ndvi") == "RdYlGn"

    def test_sar_colormap(self):
        assert TileGenerator.get_colormap_for_layer("sar") == "gray"

    def test_sar_vv_colormap(self):
        assert TileGenerator.get_colormap_for_layer("sar_vv") == "gray"

    def test_ndwi_colormap(self):
        assert TileGenerator.get_colormap_for_layer("ndwi") == "Blues"

    def test_unknown_layer_gets_viridis(self):
        assert TileGenerator.get_colormap_for_layer("unknown") == "viridis"

    def test_case_insensitive(self):
        assert TileGenerator.get_colormap_for_layer("NDVI") == "RdYlGn"


class TestTileConstants:

    def test_web_mercator_crs(self):
        assert TileGenerator.WEB_MERCATOR_CRS == "EPSG:3857"

    def test_tile_size(self):
        assert TileGenerator.TILE_SIZE == 256

    def test_zoom_range(self):
        assert TileGenerator.MIN_ZOOM == 8
        assert TileGenerator.MAX_ZOOM == 18
        assert TileGenerator.MIN_ZOOM < TileGenerator.MAX_ZOOM


class TestApplyColormap:

    def test_returns_correct_shape(self):
        data = np.random.rand(256, 256).astype(np.float32)
        result = TileGenerator._apply_colormap(data, "RdYlGn")
        assert result.shape == (256, 256, 3)
        assert result.dtype == np.uint8

    def test_all_nan_returns_black(self):
        data = np.full((256, 256), np.nan, dtype=np.float32)
        result = TileGenerator._apply_colormap(data, "gray")
        assert result.shape == (256, 256, 3)
        assert np.all(result == 0)

    def test_uniform_data_does_not_crash(self):
        data = np.full((256, 256), 0.5, dtype=np.float32)
        result = TileGenerator._apply_colormap(data, "viridis")
        assert result.shape == (256, 256, 3)


class TestTileToPixelCoords:

    def test_returns_none_for_out_of_bounds(self):
        from rasterio.transform import from_bounds

        # A small raster near Nairobi
        bounds = (4050000, -150000, 4060000, -140000)  # Web Mercator
        transform = from_bounds(*bounds, 1000, 1000)

        # Tile far away (zoom 8, tile 0,0 is top-left of world)
        result = TileGenerator._tile_to_pixel_coords(bounds, transform, zoom=8, tx=0, ty=0)
        assert result is None

    def test_returns_tuple_for_overlapping_tile(self):
        from rasterio.transform import from_bounds

        # Raster covering a large area
        bounds = (-20037508.34, -20037508.34, 20037508.34, 20037508.34)
        transform = from_bounds(*bounds, 4096, 4096)

        # Tile 0,0 at zoom 1 covers top-left quarter
        result = TileGenerator._tile_to_pixel_coords(bounds, transform, zoom=1, tx=0, ty=0)
        assert result is not None
        assert len(result) == 4
