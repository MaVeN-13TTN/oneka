"""
Sentinel-1 SAR (Synthetic Aperture Radar) processing using PyroSAR and SNAP.

This module processes Sentinel-1 GRD products to extract backscatter values
for all-weather infrastructure monitoring.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import rasterio
from loguru import logger

try:
    from pyrosar import identify, geocode
    from pyrosar.snap import ExamineSnap

    PYROSAR_AVAILABLE = True
except ImportError:
    PYROSAR_AVAILABLE = False
    logger.warning("PyroSAR not installed. SAR processing unavailable.")

from src.config import config
from src.utils import (
    extract_statistics,
    ensure_directory,
    format_scene_id,
)


class SARProcessor:
    """
    Process Sentinel-1 SAR imagery for backscatter analysis.
    """

    def __init__(self, scene_path: Path):
        """
        Initialize SAR processor.

        Args:
            scene_path: Path to Sentinel-1 SAFE or ZIP file
        """
        if not scene_path.exists():
            raise FileNotFoundError(f"Scene not found: {scene_path}")

        self.scene_path = scene_path
        self.scene_id = scene_path.stem

        if PYROSAR_AVAILABLE:
            # Identify scene metadata
            try:
                self.scene_info = identify(str(scene_path))
                logger.info(f"Scene identified: {self.scene_info.scene}")
                logger.info(f"Polarization: {self.scene_info.polarizations}")
                logger.info(f"Orbit: {self.scene_info.orbit}")
            except Exception as e:
                logger.warning(f"Failed to identify scene: {e}")
                self.scene_info = None
        else:
            self.scene_info = None

        logger.info(f"Initialized SAR processor for: {self.scene_id}")

    def check_snap_installation(self) -> bool:
        """
        Check if SNAP toolbox is installed and configured.

        Returns:
            bool: True if SNAP is available
        """
        if not PYROSAR_AVAILABLE:
            logger.error("PyroSAR not installed")
            return False

        try:
            snap = ExamineSnap()
            logger.info(f"SNAP version: {snap.version}")
            logger.info(f"SNAP path: {snap.path}")
            return True
        except Exception as e:
            logger.error(f"SNAP not properly configured: {e}")
            logger.error(
                "Install SNAP from: https://step.esa.int/main/download/snap-download/"
            )
            return False

    def geocode_scene(
        self,
        output_dir: Path,
        spacing: int = 10,
        polarizations: Optional[List[str]] = None,
    ) -> Path:
        """
        Geocode Sentinel-1 scene (calibration + terrain correction).

        Args:
            output_dir: Output directory
            spacing: Output pixel spacing in meters (default: 10m)
            polarizations: List of polarizations to process (default: ['VV', 'VH'])

        Returns:
            Path to geocoded output directory
        """
        if not PYROSAR_AVAILABLE:
            raise ImportError("PyroSAR is required but not installed")

        if not self.check_snap_installation():
            raise RuntimeError("SNAP toolbox not properly installed")

        logger.info("Starting SAR geocoding...")

        # Set default polarizations
        if polarizations is None:
            if self.scene_info and self.scene_info.polarizations:
                polarizations = self.scene_info.polarizations
            else:
                polarizations = ["VV", "VH"]

        logger.info(f"Processing polarizations: {polarizations}")

        # Ensure output directory
        ensure_directory(output_dir)

        # Geocode using PyroSAR + SNAP
        try:
            geocode(
                infile=str(self.scene_path),
                outdir=str(output_dir),
                tr=spacing,  # Target resolution
                scaling="dB",  # Output in decibels
                polarizations=polarizations,
                removeS1BorderNoise=True,  # Remove border artifacts
                terrainFlattening=True,  # Radiometric Terrain Correction (RTC)
                demName="Copernicus 30m Global DEM",  # Use Copernicus DEM
                allow_RES_OSV=True,  # Use restituted orbits if precise unavailable
            )

            logger.info(f"Geocoding complete. Output: {output_dir}")

            return output_dir

        except Exception as e:
            logger.error(f"Geocoding failed: {e}")
            raise

    def extract_backscatter(
        self,
        geocoded_dir: Path,
        lat: float,
        lon: float,
        radius_m: float = 500,
    ) -> Dict[str, Dict[str, float]]:
        """
        Extract backscatter statistics from geocoded SAR image.

        Args:
            geocoded_dir: Directory with geocoded GeoTIFFs
            lat: Center latitude
            lon: Center longitude
            radius_m: AOI radius in meters

        Returns:
            Dictionary with VV and VH statistics
        """
        logger.info(f"Extracting backscatter for AOI: ({lat}, {lon})")

        results = {}

        # Find geocoded GeoTIFFs
        geotiff_files = list(geocoded_dir.glob("*.tif"))

        if not geotiff_files:
            logger.warning(f"No GeoTIFF files found in {geocoded_dir}")
            return results

        # Process each polarization
        for geotiff_path in geotiff_files:
            # Determine polarization from filename
            filename = geotiff_path.stem.upper()

            if "_VV_" in filename or filename.endswith("_VV"):
                pol = "VV"
            elif "_VH_" in filename or filename.endswith("_VH"):
                pol = "VH"
            elif "_HH_" in filename or filename.endswith("_HH"):
                pol = "HH"
            elif "_HV_" in filename or filename.endswith("_HV"):
                pol = "HV"
            else:
                logger.warning(f"Unknown polarization in file: {filename}")
                continue

            logger.info(f"Processing {pol} polarization: {geotiff_path.name}")

            # Read GeoTIFF
            with rasterio.open(geotiff_path) as src:
                data = src.read(1)

                # Mask invalid values (nodata, inf, etc.)
                data = np.where(np.isfinite(data), data, np.nan)

                # Extract statistics
                stats = extract_statistics(data)

                results[pol] = stats

                logger.info(
                    f"{pol} backscatter: mean={stats['mean']:.2f} dB, "
                    f"std={stats['std']:.2f} dB"
                )

        return results

    def process(
        self,
        lat: float,
        lon: float,
        output_dir: Path,
    ) -> Dict:
        """
        Complete SAR processing workflow.

        Args:
            lat: Center latitude
            lon: Center longitude
            output_dir: Output directory

        Returns:
            Dictionary with results
        """
        logger.info("Starting SAR processing workflow...")

        # Ensure output directory
        ensure_directory(output_dir)

        # Geocode scene
        geocoded_dir = output_dir / f"{self.scene_id}_geocoded"
        self.geocode_scene(geocoded_dir)

        # Extract backscatter
        backscatter_stats = self.extract_backscatter(
            geocoded_dir=geocoded_dir,
            lat=lat,
            lon=lon,
            radius_m=config.AOI_RADIUS,
        )

        # Prepare results
        results = {
            "scene_id": self.scene_id,
            "sensor": "Sentinel-1",
            "backscatter": backscatter_stats,
            "geocoded_dir": str(geocoded_dir),
            "processed_date": datetime.now().isoformat(),
        }

        logger.info("SAR processing complete")

        return results


def main():
    """
    Command-line interface for SAR processing.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Process Sentinel-1 SAR imagery for backscatter analysis"
    )

    parser.add_argument(
        "--scene", type=str, required=True, help="Path to Sentinel-1 SAFE or ZIP"
    )
    parser.add_argument("--lat", type=float, required=True, help="Center latitude")
    parser.add_argument("--lon", type=float, required=True, help="Center longitude")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    parser.add_argument(
        "--check-snap", action="store_true", help="Check SNAP installation and exit"
    )

    args = parser.parse_args()

    # Set up output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = config.PROCESSED_DATA_DIR

    # Initialize processor
    scene_path = Path(args.scene)
    processor = SARProcessor(scene_path)

    # Check SNAP installation
    if args.check_snap:
        if processor.check_snap_installation():
            logger.info("✅ SNAP is properly installed and configured")
        else:
            logger.error("❌ SNAP installation check failed")
        return

    # Process
    results = processor.process(
        lat=args.lat,
        lon=args.lon,
        output_dir=output_dir,
    )

    # Display results
    logger.info("\n" + "=" * 60)
    logger.info("SAR PROCESSING RESULTS")
    logger.info("=" * 60)
    logger.info(f"Scene: {results['scene_id']}")

    for pol, stats in results["backscatter"].items():
        logger.info(f"\n{pol} Polarization:")
        logger.info(f"  Mean: {stats['mean']:.2f} dB")
        logger.info(f"  Std: {stats['std']:.2f} dB")
        logger.info(f"  Min: {stats['min']:.2f} dB")
        logger.info(f"  Max: {stats['max']:.2f} dB")

    logger.info(f"\nGeocoded: {results['geocoded_dir']}")
    logger.info("=" * 60)


if __name__ == "__main__":
    from src.utils import setup_logger

    setup_logger(level=config.LOG_LEVEL)
    main()
