"""
XYZ Tile generation from processed GeoTIFF imagery.

This module converts processed NDVI, SAR, and other raster data into XYZ tile
pyramids optimized for web mapping (Leaflet, Mapbox, etc.).

Key features:
  - Reproject rasters to Web Mercator (EPSG:3857)
  - Generate tile pyramid for zoom levels 8-18
  - Apply scientific colormaps (RdYlGn for NDVI, grayscale for SAR)
  - Handle NaN values as transparent pixels
  - Normalize bands to uint8 (0-255) with percentile clipping

Tile output structure:
  {output_dir}/
    {z}/
      {x}/
        {y}.png
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.plot import reshape_as_image
from rasterio.transform import Affine, from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling, calculate_default_transform
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import cv2
from loguru import logger

try:
    from src.config import config
except ImportError:
    config = None


class TileGenerator:
    """
    Generate XYZ tile pyramids from GeoTIFF rasters.

    Converts single-band or multi-band rasters into Web Mercator-projected
    tile pyramids with scientific colormaps applied.
    """

    # Web Mercator EPSG code
    WEB_MERCATOR_CRS = "EPSG:3857"

    # Standard zoom levels for web maps
    MIN_ZOOM = 8
    MAX_ZOOM = 18

    # Tile size (standard for web mapping)
    TILE_SIZE = 256

    def __init__(self, geotiff_path: str | Path, band_index: int = 1):
        """
        Initialize TileGenerator with a GeoTIFF raster.

        Args:
            geotiff_path: Path to processed GeoTIFF (can be local or S3 via rasterio)
            band_index: Band number to use (1-indexed, default: 1)

        Raises:
            FileNotFoundError: If GeoTIFF file doesn't exist
            ValueError: If band_index is invalid or GeoTIFF has no georeferencing
        """
        self.geotiff_path = Path(geotiff_path)
        self.band_index = band_index

        # Validate file exists (for local paths)
        if self.geotiff_path.exists():
            logger.info(f"Initialized TileGenerator for: {self.geotiff_path}")
        else:
            logger.warning(f"GeoTIFF path may be remote or S3 path: {self.geotiff_path}")

        # Validate on first access (deferred for S3 compatibility)
        self._validated = False

    def _validate_geotiff(self) -> None:
        """
        Validate GeoTIFF is readable and has georeferencing.

        Raises:
            FileNotFoundError: If file cannot be opened
            ValueError: If missing georeferencing or invalid band
        """
        try:
            with rasterio.open(str(self.geotiff_path)) as src:
                if src.crs is None:
                    raise ValueError(
                        f"GeoTIFF missing CRS (no georeferencing): {self.geotiff_path}"
                    )

                if self.band_index > src.count or self.band_index < 1:
                    raise ValueError(
                        f"Invalid band {self.band_index}. "
                        f"GeoTIFF has {src.count} band(s)."
                    )

                self._metadata = {
                    "crs": src.crs,
                    "bounds": src.bounds,
                    "width": src.width,
                    "height": src.height,
                    "transform": src.transform,
                    "band_count": src.count,
                }

                logger.info(
                    f"Validated GeoTIFF: {src.width}x{src.height}, "
                    f"CRS={src.crs}, bands={src.count}"
                )
        except rasterio.errors.RasterioIOError as e:
            raise FileNotFoundError(
                f"Cannot read GeoTIFF at {self.geotiff_path}: {e}"
            ) from e

        self._validated = True

    @staticmethod
    def generate_ndvi_tiles(
        geotiff_path: str | Path,
        output_dir: str | Path,
        colormap: str = "RdYlGn",
        z_min: int = 8,
        z_max: int = 18,
    ) -> dict:
        """
        Generate NDVI tile pyramid from GeoTIFF.

        Creates XYZ tile structure with Red-Yellow-Green colormap.

        Args:
            geotiff_path: Path to NDVI GeoTIFF (-1 to 1 range)
            output_dir: Output directory for tiles
            colormap: Matplotlib colormap name (default: 'RdYlGn')
            z_min: Minimum zoom level (default: 8)
            z_max: Maximum zoom level (default: 18)

        Returns:
            dict with keys:
                - tile_count: Number of tiles generated
                - s3_prefix: Suggested S3 prefix (e.g., 'tiles/{uuid}/ndvi')
                - base_url: Suggested base URL template
                - z_range: (z_min, z_max)
                - error: None or error message

        Example:
            result = TileGenerator.generate_ndvi_tiles(
                'satellite.tif', '/tmp/tiles',
                colormap='RdYlGn', z_min=8, z_max=16
            )
        """
        try:
            generator = TileGenerator(geotiff_path)
            return generator._generate_tiles(
                layer_type="ndvi",
                output_dir=output_dir,
                colormap=colormap,
                z_min=z_min,
                z_max=z_max,
            )
        except Exception as e:
            logger.exception(f"Failed to generate NDVI tiles: {e}")
            return {
                "tile_count": 0,
                "error": str(e),
                "z_range": (z_min, z_max),
            }

    @staticmethod
    def generate_sar_tiles(
        geotiff_path: str | Path,
        output_dir: str | Path,
        colormap: str = "gray",
        z_min: int = 8,
        z_max: int = 18,
    ) -> dict:
        """
        Generate SAR tile pyramid from GeoTIFF.

        Creates XYZ tile structure with grayscale colormap.

        Args:
            geotiff_path: Path to SAR backscatter GeoTIFF (typically -30 to 10 dB)
            output_dir: Output directory for tiles
            colormap: Matplotlib colormap name (default: 'gray')
            z_min: Minimum zoom level (default: 8)
            z_max: Maximum zoom level (default: 18)

        Returns:
            dict (same structure as generate_ndvi_tiles)
        """
        try:
            generator = TileGenerator(geotiff_path)
            return generator._generate_tiles(
                layer_type="sar",
                output_dir=output_dir,
                colormap=colormap,
                z_min=z_min,
                z_max=z_max,
            )
        except Exception as e:
            logger.exception(f"Failed to generate SAR tiles: {e}")
            return {
                "tile_count": 0,
                "error": str(e),
                "z_range": (z_min, z_max),
            }

    def _generate_tiles(
        self,
        layer_type: str,
        output_dir: str | Path,
        colormap: str,
        z_min: int,
        z_max: int,
    ) -> dict:
        """
        Generate tile pyramid for given layer type.

        Internal method coordinating the full pipeline:
          1. Validate GeoTIFF
          2. Reproject to Web Mercator
          3. For each zoom level:
             a. Divide into 256x256 tiles
             b. Normalize band data
             c. Apply colormap
             d. Encode PNG
             e. Write {z}/{x}/{y}.png

        Args:
            layer_type: 'ndvi', 'sar', etc.
            output_dir: Output directory
            colormap: Matplotlib colormap name
            z_min, z_max: Zoom range

        Returns:
            dict with tile_count and metadata
        """
        if not self._validated:
            self._validate_geotiff()

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Generating {layer_type.upper()} tiles: "
            f"zoom {z_min}-{z_max}, colormap={colormap}"
        )

        tile_count = 0
        errors = []

        try:
            # Reproject to Web Mercator
            with self._reproject_to_web_mercator() as src:
                # Generate tiles for each zoom level
                for z in range(z_min, z_max + 1):
                    try:
                        z_tiles = self._generate_zoom_level(
                            src, z, output_path, colormap, layer_type
                        )
                        tile_count += z_tiles
                        logger.info(f"  Generated {z_tiles} tiles at zoom {z}")
                    except Exception as e:
                        msg = f"Error at zoom {z}: {e}"
                        logger.warning(msg)
                        errors.append(msg)

        except Exception as e:
            logger.exception(f"Projection/tiling failed: {e}")
            errors.append(f"Reprojection failed: {e}")

        result = {
            "tile_count": tile_count,
            "z_range": (z_min, z_max),
            "output_dir": str(output_path),
            "layer_type": layer_type,
            "colormap": colormap,
        }

        if errors:
            result["warnings"] = errors
            logger.warning(f"Generated {tile_count} tiles with {len(errors)} warning(s)")
        else:
            logger.info(f"Successfully generated {tile_count} tiles")

        return result

    def _reproject_to_web_mercator(self):
        """
        Reproject raster to Web Mercator (EPSG:3857).

        Returns:
            Context manager with reprojected rasterio dataset.
        """
        return WarpedVRT(
            rasterio.open(str(self.geotiff_path)),
            crs=self.WEB_MERCATOR_CRS,
            resampling=Resampling.bilinear,
        )

    def _generate_zoom_level(
        self,
        src,
        zoom: int,
        output_dir: Path,
        colormap_name: str,
        layer_type: str,
    ) -> int:
        """
        Generate tiles for a single zoom level.

        Computes Web Mercator tile coordinates and reads windowed data from
        the reprojected raster, then encodes as PNG.

        Args:
            src: Opened rasterio dataset (Web Mercator-projected)
            zoom: Zoom level (0-28)
            output_dir: Output directory root
            colormap_name: Matplotlib colormap
            layer_type: 'ndvi', 'sar', etc.

        Returns:
            Number of tiles generated at this zoom level
        """
        # Compute tile grid for this zoom level
        n_tiles = 2 ** zoom  # 2^zoom x 2^zoom tiles at this level

        # Get Web Mercator bounds
        bounds = src.bounds
        transform = src.transform

        tile_count = 0

        # Iterate through all possible tiles at this zoom
        for tx in range(n_tiles):
            for ty in range(n_tiles):
                try:
                    # Compute pixel coordinates for this tile
                    pixel_bounds = self._tile_to_pixel_coords(
                        bounds, transform, zoom, tx, ty
                    )

                    if pixel_bounds is None:
                        continue  # Tile outside raster bounds

                    # Read tile data
                    tile_data = self._read_tile_data(
                        src, pixel_bounds, layer_type
                    )

                    if tile_data is None:
                        continue

                    # Normalize and apply colormap
                    rgb_image = self._apply_colormap(tile_data, colormap_name)

                    # Write PNG
                    z_dir = output_dir / str(zoom) / str(tx)
                    z_dir.mkdir(parents=True, exist_ok=True)
                    tile_path = z_dir / f"{ty}.png"

                    cv2.imwrite(str(tile_path), rgb_image)
                    tile_count += 1

                except Exception as e:
                    logger.debug(f"Failed to generate tile z{zoom}/x{tx}/y{ty}: {e}")

        return tile_count

    @staticmethod
    def _tile_to_pixel_coords(
        bounds, transform, zoom: int, tx: int, ty: int
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Convert Web Mercator tile coordinates to pixel bounds in raster.

        Args:
            bounds: Raster bounds (minx, miny, maxx, maxy)
            transform: Rasterio affine transform
            zoom: Zoom level
            tx, ty: Tile coordinates

        Returns:
            (row_start, col_start, row_end, col_end) or None if outside bounds
        """
        # Compute tile extent in Web Mercator
        n_tiles = 2 ** zoom
        tile_size_degrees = 2 * 20037508.34 / n_tiles  # Web Mercator range / tiles

        minx, miny, maxx, maxy = bounds
        tile_minx = -20037508.34 + tx * tile_size_degrees
        tile_maxy = 20037508.34 - ty * tile_size_degrees
        tile_maxx = tile_minx + tile_size_degrees
        tile_miny = tile_maxy - tile_size_degrees

        # Check if tile overlaps raster
        if (
            tile_maxx < minx
            or tile_minx > maxx
            or tile_maxy < miny
            or tile_miny > maxy
        ):
            return None

        # Convert to pixel coordinates using transform
        row_start, col_start = ~transform * (tile_maxx, tile_maxy)
        row_end, col_end = ~transform * (tile_minx, tile_miny)

        return (
            max(0, int(row_start)),
            max(0, int(col_start)),
            int(row_end) + 1,
            int(col_end) + 1,
        )

    @staticmethod
    def _read_tile_data(src, pixel_bounds, layer_type: str) -> Optional[np.ndarray]:
        """
        Read tile data window from raster.

        Args:
            src: Opened rasterio dataset
            pixel_bounds: (row_start, col_start, row_end, col_end)
            layer_type: 'ndvi', 'sar', etc.

        Returns:
            Normalized uint8 array (256x256x3) or None if empty
        """
        row_start, col_start, row_end, col_end = pixel_bounds

        try:
            # Clip to raster bounds
            row_start = max(0, row_start)
            col_start = max(0, col_start)
            row_end = min(src.height, row_end)
            col_end = min(src.width, col_end)

            if row_start >= row_end or col_start >= col_end:
                return None

            # Read band data
            data = src.read(1, window=((row_start, row_end), (col_start, col_end)))

            if data.size == 0 or np.all(np.isnan(data)):
                return None

            # Resize to 256x256 if needed
            if data.shape != (256, 256):
                data = cv2.resize(data, (256, 256), interpolation=cv2.INTER_LINEAR)

            return data

        except Exception as e:
            logger.debug(f"Failed to read tile data: {e}")
            return None

    @staticmethod
    def _apply_colormap(
        data: np.ndarray, colormap_name: str
    ) -> np.ndarray:
        """
        Apply colormap and normalize band to RGB image.

        Handles NaN values as fully transparent pixels.

        Args:
            data: 2D array (256x256) with float values
            colormap_name: Matplotlib colormap name ('RdYlGn', 'gray', etc.)

        Returns:
            RGB image as uint8 (256x256x3)
        """
        # Create NaN mask (True where valid data exists)
        nan_mask = np.isfinite(data)

        # Normalize data to 0-1 range using percentile clipping
        if nan_mask.sum() == 0:
            # All NaN
            return np.zeros((256, 256, 3), dtype=np.uint8)

        p2, p98 = np.nanpercentile(data[nan_mask], [2, 98])
        normalized = np.clip((data - p2) / (p98 - p2 + 1e-10), 0, 1)

        # Apply colormap
        cm = plt.get_cmap(colormap_name)
        colored = cm(normalized)  # RGBA (0-1)

        # Convert to uint8 RGB
        rgb = (colored[:, :, :3] * 255).astype(np.uint8)

        # Convert to BGR for OpenCV
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        return bgr

    @staticmethod
    def get_colormap_for_layer(layer_type: str) -> str:
        """
        Get appropriate colormap for layer type.

        Args:
            layer_type: 'ndvi', 'sar', 'ndwi', etc.

        Returns:
            Matplotlib colormap name
        """
        colormaps = {
            "ndvi": "RdYlGn",  # Red-Yellow-Green diverging
            "sar": "gray",  # Grayscale
            "ndwi": "Blues",  # Water: blue shades
            "sar_vv": "gray",
            "sar_vh": "gray",
        }
        return colormaps.get(layer_type.lower(), "viridis")
