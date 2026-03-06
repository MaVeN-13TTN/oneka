"""
NDVI (Normalized Difference Vegetation Index) calculation from Sentinel-2 imagery.

This module processes Sentinel-2 L2A scenes to calculate NDVI and detect
vegetation clearing patterns indicative of construction activity.
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
import matplotlib.pyplot as plt
from loguru import logger

try:
    from satpy import Scene

    SATPY_AVAILABLE = True
except ImportError:
    SATPY_AVAILABLE = False
    logger.warning("Satpy not installed. Some features may be unavailable.")

from src.config import config
from src.utils import (
    calculate_ndvi,
    extract_statistics,
    create_output_filename,
    ensure_directory,
    format_scene_id,
)


def compute_ndvi_slope(
    dates: List[str], ndvi_means: List[float]
) -> Optional[float]:
    """
    Compute linear regression slope of NDVI over time.

    Uses numpy polyfit on (months elapsed, ndvi_mean) pairs.  Any NaN values
    are excluded before fitting.  Requires at least 2 valid observations.

    Args:
        dates:      ISO-8601 date strings ('YYYY-MM-DD'), parallel to ndvi_means.
        ndvi_means: Corresponding mean NDVI values.

    Returns:
        Slope in NDVI units per month, or None if < 2 valid data points.

    Interpretation:
        Negative slope → NDVI declining over time → land clearing / construction
        Positive slope → NDVI increasing → vegetation recovery, no construction
    """
    if len(dates) < 2 or len(ndvi_means) < 2:
        return None

    base = datetime.strptime(dates[0], "%Y-%m-%d")
    x = np.array(
        [(datetime.strptime(d, "%Y-%m-%d") - base).days / 30.44 for d in dates],
        dtype=float,
    )
    y = np.array(ndvi_means, dtype=float)

    valid = np.isfinite(y)
    if valid.sum() < 2:
        return None

    coeffs = np.polyfit(x[valid], y[valid], 1)
    return float(coeffs[0])  # slope in NDVI/month


class NDVIProcessor:
    """
    Process Sentinel-2 imagery to calculate NDVI and detect construction activity.
    """

    def __init__(self, scene_path: Path):
        """
        Initialize NDVI processor.

        Args:
            scene_path: Path to Sentinel-2 SAFE directory
        """
        if not scene_path.exists():
            raise FileNotFoundError(f"Scene not found: {scene_path}")

        if not scene_path.name.endswith(".SAFE"):
            raise ValueError(f"Invalid SAFE directory: {scene_path}")

        self.scene_path = scene_path
        self.scene_id = scene_path.stem

        logger.info(f"Initialized NDVI processor for: {self.scene_id}")

    def load_bands_satpy(self) -> Tuple[np.ndarray, dict]:
        """
        Load Red (B04) and NIR (B08) bands using Satpy.

        Returns:
            Tuple of (red array, nir array, metadata dict)
        """
        if not SATPY_AVAILABLE:
            raise ImportError("Satpy is required but not installed")

        logger.info("Loading bands with Satpy...")

        scn = Scene(reader="msi_safe", filenames=[str(self.scene_path)])
        scn.load(["B04", "B08"])

        red = scn["B04"].values
        nir = scn["B08"].values

        metadata = {
            "crs": scn["B04"].attrs.get("area").crs,
            "transform": scn["B04"].attrs.get("area").area_extent,
            "resolution": scn["B04"].attrs.get("resolution"),
        }

        logger.info(f"Loaded bands: Red={red.shape}, NIR={nir.shape}")
        return (red, nir, metadata)

    def load_bands_rasterio(self) -> Tuple[np.ndarray, np.ndarray, dict]:
        """
        Load Red and NIR bands using rasterio.

        Returns:
            Tuple of (red_array, nir_array, metadata dict)
        """
        logger.info("Loading bands with rasterio...")

        granule_dir = self.scene_path / "GRANULE"
        if not granule_dir.exists():
            raise FileNotFoundError(
                f"GRANULE directory not found in {self.scene_path}"
            )

        granules = list(granule_dir.iterdir())
        if not granules:
            raise FileNotFoundError("No granules found in SAFE directory")

        img_data_dir = granules[0] / "IMG_DATA" / "R10m"

        b04_files = list(img_data_dir.glob("*B04_10m.jp2"))
        b08_files = list(img_data_dir.glob("*B08_10m.jp2"))

        if not b04_files or not b08_files:
            raise FileNotFoundError("B04 or B08 band files not found")

        with rasterio.open(b04_files[0]) as src:
            red = src.read(1).astype(np.float32)
            transform = src.transform
            crs = src.crs
            profile = src.profile

        with rasterio.open(b08_files[0]) as src:
            nir = src.read(1).astype(np.float32)

        metadata = {"crs": crs, "transform": transform, "profile": profile}

        logger.info(f"Loaded bands: Red={red.shape}, NIR={nir.shape}")
        return (red, nir, metadata)

    def calculate_ndvi(
        self,
        red: np.ndarray,
        nir: np.ndarray,
        mask_clouds: bool = True,
    ) -> np.ndarray:
        """Calculate NDVI from Red and NIR bands."""
        logger.info("Calculating NDVI...")
        ndvi = calculate_ndvi(nir, red)
        ndvi = np.where(np.isfinite(ndvi), ndvi, np.nan)
        logger.info(f"NDVI range: {np.nanmin(ndvi):.3f} to {np.nanmax(ndvi):.3f}")
        return ndvi

    def extract_aoi_statistics(
        self,
        ndvi: np.ndarray,
        lat: float,
        lon: float,
        radius_m: float = 500,
        metadata: dict = None,
    ) -> Dict[str, float]:
        """
        Extract NDVI statistics for the 500 m AOI around the project site.

        Applies a circular buffer centred on (lat, lon) using rasterio.mask.
        The NDVI array is written to a temporary GeoTIFF, clipped with the
        buffer geometry, then statistics are extracted from the clipped pixels.

        Falls back to full-scene statistics if spatial masking fails.

        Args:
            ndvi:     Full-scene NDVI float array.
            lat:      Project site WGS-84 latitude.
            lon:      Project site WGS-84 longitude.
            radius_m: Buffer radius in metres (default 500 per config.AOI_RADIUS).
            metadata: Dict with 'crs' and 'profile' from rasterio.

        Returns:
            Dict: mean, std, min, max, median, p25, p75.
        """
        logger.info(
            "Extracting AOI statistics: (%.5f, %.5f), radius=%dm",
            lat,
            lon,
            radius_m,
        )

        if metadata is None:
            logger.warning("No metadata provided — using full-scene statistics")
            return extract_statistics(ndvi)

        try:
            import pyproj
            from shapely.geometry import Point, mapping
            from shapely.ops import transform as shapely_transform

            crs = metadata.get("crs")
            profile = metadata.get("profile", {})

            if crs is None or not profile:
                raise ValueError("Incomplete metadata (missing crs or profile)")

            # Project the site centre from WGS-84 to the scene's CRS (e.g., UTM)
            wgs84 = pyproj.CRS("EPSG:4326")
            scene_crs = pyproj.CRS(crs)
            transformer = pyproj.Transformer.from_crs(
                wgs84, scene_crs, always_xy=True
            )

            point_proj = shapely_transform(
                transformer.transform, Point(lon, lat)
            )
            # buffer() is in scene CRS units (metres for UTM or EASE-Grid)
            aoi_geom = point_proj.buffer(radius_m)

            # Write NDVI to a temp GeoTIFF, apply rasterio mask, extract stats
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".tif")
            os.close(tmp_fd)
            try:
                profile_copy = dict(profile)
                profile_copy.update(
                    dtype=rasterio.float32, count=1, nodata=float("nan")
                )
                with rasterio.open(tmp_path, "w", **profile_copy) as dst:
                    dst.write(ndvi.astype(np.float32), 1)

                with rasterio.open(tmp_path) as src:
                    masked, _ = mask(
                        src,
                        [mapping(aoi_geom)],
                        crop=True,
                        all_touched=True,
                        nodata=float("nan"),
                    )
                aoi_ndvi = masked[0]
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            stats = extract_statistics(aoi_ndvi)
            logger.info(
                "AOI NDVI — mean=%.3f, std=%.3f",
                stats.get("mean", float("nan")),
                stats.get("std", float("nan")),
            )
            return stats

        except Exception as exc:
            logger.warning(
                "AOI masking failed (%s) — using full-scene statistics", exc
            )
            return extract_statistics(ndvi)

    def save_geotiff(
        self,
        ndvi: np.ndarray,
        output_path: Path,
        metadata: dict,
    ) -> Path:
        """Save NDVI as a compressed GeoTIFF."""
        logger.info(f"Saving GeoTIFF: {output_path}")

        profile = metadata.get("profile", {})
        profile.update(dtype=rasterio.float32, count=1, compress="lzw", nodata=np.nan)

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(ndvi.astype(np.float32), 1)

        logger.info(f"Saved: {output_path}")
        return output_path

    def create_visualization(
        self,
        ndvi: np.ndarray,
        output_path: Path,
        title: Optional[str] = None,
    ) -> Path:
        """Create an RdYlGn colour-coded NDVI PNG."""
        logger.info(f"Creating visualization: {output_path}")

        fig, ax = plt.subplots(figsize=(10, 8))
        cmap = plt.get_cmap("RdYlGn")
        im = ax.imshow(ndvi, cmap=cmap, vmin=-0.2, vmax=0.8)
        cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("NDVI", rotation=270, labelpad=20)
        ax.set_title(title or f"NDVI - {self.scene_id}", fontsize=14)
        ax.axis("off")
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        logger.info(f"Saved visualization: {output_path}")
        return output_path

    def process(
        self,
        lat: float,
        lon: float,
        output_dir: Path,
        use_satpy: bool = False,
    ) -> Dict:
        """
        Complete NDVI processing workflow.

        Args:
            lat:        Site centre latitude (WGS-84).
            lon:        Site centre longitude (WGS-84).
            output_dir: Directory for GeoTIFF and PNG outputs.
            use_satpy:  Use Satpy (True) or rasterio (False, default).

        Returns:
            Dict with scene_id, sensor, statistics, geotiff_path,
            visualization_path, processed_date.
        """
        logger.info("Starting NDVI processing workflow...")
        ensure_directory(output_dir)

        if use_satpy and SATPY_AVAILABLE:
            red, nir, metadata = self.load_bands_satpy()
        else:
            red, nir, metadata = self.load_bands_rasterio()

        ndvi = self.calculate_ndvi(red, nir)

        # Extract stats within the 500 m AOI polygon
        stats = self.extract_aoi_statistics(
            ndvi=ndvi,
            lat=lat,
            lon=lon,
            radius_m=config.AOI_RADIUS,
            metadata=metadata,
        )

        geotiff_path = output_dir / f"{self.scene_id}_NDVI.tif"
        self.save_geotiff(ndvi, geotiff_path, metadata)

        viz_path = output_dir / f"{self.scene_id}_NDVI.png"
        self.create_visualization(ndvi, viz_path)

        results = {
            "scene_id": self.scene_id,
            "sensor": "Sentinel-2",
            "statistics": stats,
            "geotiff_path": str(geotiff_path),
            "visualization_path": str(viz_path),
            "processed_date": datetime.now().isoformat(),
        }

        logger.info("NDVI processing complete")
        return results


def main():
    """Command-line interface for NDVI processing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Calculate NDVI from Sentinel-2 imagery"
    )
    parser.add_argument("--scene", type=str, required=True,
                        help="Path to Sentinel-2 SAFE directory")
    parser.add_argument("--lat", type=float, required=True, help="Centre latitude")
    parser.add_argument("--lon", type=float, required=True, help="Centre longitude")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    parser.add_argument("--use-satpy", action="store_true",
                        help="Use Satpy instead of rasterio")

    args = parser.parse_args()
    output_dir = Path(args.output) if args.output else config.PROCESSED_DATA_DIR

    processor = NDVIProcessor(Path(args.scene))
    results = processor.process(
        lat=args.lat, lon=args.lon,
        output_dir=output_dir, use_satpy=args.use_satpy,
    )

    logger.info("\n" + "=" * 60)
    logger.info("NDVI PROCESSING RESULTS")
    logger.info("=" * 60)
    logger.info(f"Scene: {results['scene_id']}")
    logger.info(f"NDVI Mean: {results['statistics']['mean']:.3f}")
    logger.info(f"NDVI Std:  {results['statistics']['std']:.3f}")
    logger.info(f"GeoTIFF:   {results['geotiff_path']}")
    logger.info("=" * 60)


if __name__ == "__main__":
    from src.utils import setup_logger

    setup_logger(level=config.LOG_LEVEL)
    main()
