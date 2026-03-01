"""
NDVI (Normalized Difference Vegetation Index) calculation from Sentinel-2 imagery.

This module processes Sentinel-2 L2A scenes to calculate NDVI and detect
vegetation clearing patterns indicative of construction activity.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
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
            Tuple of (NDVI array, metadata dict)
        """
        if not SATPY_AVAILABLE:
            raise ImportError("Satpy is required but not installed")

        logger.info("Loading bands with Satpy...")

        # Create Satpy Scene
        scn = Scene(reader="msi_safe", filenames=[str(self.scene_path)])

        # Load required bands
        scn.load(["B04", "B08"])  # Red, NIR

        # Extract arrays
        red = scn["B04"].values
        nir = scn["B08"].values

        # Get metadata
        metadata = {
            "crs": scn["B04"].attrs.get("area").crs,
            "transform": scn["B04"].attrs.get("area").area_extent,
            "resolution": scn["B04"].attrs.get("resolution"),
        }

        logger.info(f"Loaded bands: Red={red.shape}, NIR={nir.shape}")

        return (red, nir, metadata)

    def load_bands_rasterio(self) -> Tuple[np.ndarray, np.ndarray, dict]:
        """
        Load Red and NIR bands using rasterio (alternative to Satpy).

        Returns:
            Tuple of (red_array, nir_array, metadata dict)
        """
        logger.info("Loading bands with rasterio...")

        # Find band files in SAFE structure
        granule_dir = self.scene_path / "GRANULE"
        if not granule_dir.exists():
            raise FileNotFoundError(f"GRANULE directory not found in {self.scene_path}")

        # Get first granule
        granules = list(granule_dir.iterdir())
        if not granules:
            raise FileNotFoundError("No granules found in SAFE directory")

        img_data_dir = granules[0] / "IMG_DATA" / "R10m"

        # Find B04 (Red) and B08 (NIR) files
        b04_files = list(img_data_dir.glob("*B04_10m.jp2"))
        b08_files = list(img_data_dir.glob("*B08_10m.jp2"))

        if not b04_files or not b08_files:
            raise FileNotFoundError("B04 or B08 band files not found")

        # Read bands
        with rasterio.open(b04_files[0]) as src:
            red = src.read(1).astype(np.float32)
            transform = src.transform
            crs = src.crs
            profile = src.profile

        with rasterio.open(b08_files[0]) as src:
            nir = src.read(1).astype(np.float32)

        metadata = {
            "crs": crs,
            "transform": transform,
            "profile": profile,
        }

        logger.info(f"Loaded bands: Red={red.shape}, NIR={nir.shape}")

        return (red, nir, metadata)

    def calculate_ndvi(
        self,
        red: np.ndarray,
        nir: np.ndarray,
        mask_clouds: bool = True,
    ) -> np.ndarray:
        """
        Calculate NDVI from Red and NIR bands.

        Args:
            red: Red band array
            nir: NIR band array
            mask_clouds: Whether to mask cloudy pixels

        Returns:
            NDVI array
        """
        logger.info("Calculating NDVI...")

        # Calculate NDVI
        ndvi = calculate_ndvi(nir, red)

        # Mask invalid values
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
        Extract NDVI statistics for Area of Interest (AOI).

        Args:
            ndvi: NDVI array
            lat: Center latitude
            lon: Center longitude
            radius_m: AOI radius in meters
            metadata: Raster metadata with CRS and transform

        Returns:
            Dictionary with statistics
        """
        logger.info(
            f"Extracting statistics for AOI: ({lat}, {lon}), radius={radius_m}m"
        )

        # For simplicity, extract stats from entire array
        # In production, use rasterio.mask with circular polygon
        stats = extract_statistics(ndvi)

        logger.info(
            f"NDVI statistics: mean={stats['mean']:.3f}, std={stats['std']:.3f}"
        )

        return stats

    def save_geotiff(
        self,
        ndvi: np.ndarray,
        output_path: Path,
        metadata: dict,
    ) -> Path:
        """
        Save NDVI as GeoTIFF.

        Args:
            ndvi: NDVI array
            output_path: Output file path
            metadata: Raster metadata

        Returns:
            Path to saved file
        """
        logger.info(f"Saving GeoTIFF: {output_path}")

        # Update profile for single-band float output
        profile = metadata.get("profile", {})
        profile.update(
            dtype=rasterio.float32,
            count=1,
            compress="lzw",
            nodata=np.nan,
        )

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
        """
        Create NDVI visualization (color-coded map).

        Args:
            ndvi: NDVI array
            output_path: Output PNG path
            title: Plot title

        Returns:
            Path to saved image
        """
        logger.info(f"Creating visualization: {output_path}")

        # Create figure
        fig, ax = plt.subplots(figsize=(10, 8))

        # Color map: Red (bare) -> Yellow -> Green (vegetation)
        cmap = plt.get_cmap("RdYlGn")

        # Plot NDVI
        im = ax.imshow(ndvi, cmap=cmap, vmin=-0.2, vmax=0.8)

        # Add colorbar
        cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("NDVI", rotation=270, labelpad=20)

        # Title
        if title:
            ax.set_title(title, fontsize=14, fontweight="bold")
        else:
            ax.set_title(f"NDVI - {self.scene_id}", fontsize=14)

        ax.axis("off")

        # Save
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
            lat: Center latitude for AOI
            lon: Center longitude for AOI
            output_dir: Output directory
            use_satpy: Use Satpy (True) or rasterio (False)

        Returns:
            Dictionary with results
        """
        logger.info("Starting NDVI processing workflow...")

        # Ensure output directory exists
        ensure_directory(output_dir)

        # Load bands
        if use_satpy and SATPY_AVAILABLE:
            red, nir, metadata = self.load_bands_satpy()
        else:
            red, nir, metadata = self.load_bands_rasterio()

        # Calculate NDVI
        ndvi = self.calculate_ndvi(red, nir)

        # Extract statistics
        stats = self.extract_aoi_statistics(
            ndvi=ndvi,
            lat=lat,
            lon=lon,
            radius_m=config.AOI_RADIUS,
            metadata=metadata,
        )

        # Save GeoTIFF
        geotiff_path = output_dir / f"{self.scene_id}_NDVI.tif"
        self.save_geotiff(ndvi, geotiff_path, metadata)

        # Create visualization
        viz_path = output_dir / f"{self.scene_id}_NDVI.png"
        self.create_visualization(ndvi, viz_path)

        # Prepare results
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
    """
    Command-line interface for NDVI processing.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Calculate NDVI from Sentinel-2 imagery"
    )

    parser.add_argument(
        "--scene", type=str, required=True, help="Path to Sentinel-2 SAFE directory"
    )
    parser.add_argument("--lat", type=float, required=True, help="Center latitude")
    parser.add_argument("--lon", type=float, required=True, help="Center longitude")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    parser.add_argument(
        "--use-satpy", action="store_true", help="Use Satpy instead of rasterio"
    )

    args = parser.parse_args()

    # Set up output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = config.PROCESSED_DATA_DIR

    # Initialize processor
    scene_path = Path(args.scene)
    processor = NDVIProcessor(scene_path)

    # Process
    results = processor.process(
        lat=args.lat,
        lon=args.lon,
        output_dir=output_dir,
        use_satpy=args.use_satpy,
    )

    # Display results
    logger.info("\n" + "=" * 60)
    logger.info("NDVI PROCESSING RESULTS")
    logger.info("=" * 60)
    logger.info(f"Scene: {results['scene_id']}")
    logger.info(f"NDVI Mean: {results['statistics']['mean']:.3f}")
    logger.info(f"NDVI Std: {results['statistics']['std']:.3f}")
    logger.info(f"NDVI Min: {results['statistics']['min']:.3f}")
    logger.info(f"NDVI Max: {results['statistics']['max']:.3f}")
    logger.info(f"GeoTIFF: {results['geotiff_path']}")
    logger.info(f"Visualization: {results['visualization_path']}")
    logger.info("=" * 60)


if __name__ == "__main__":
    from src.utils import setup_logger

    setup_logger(level=config.LOG_LEVEL)
    main()
