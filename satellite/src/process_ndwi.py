"""
NDWI (Normalized Difference Water Index) calculation from Sentinel-2 imagery.

Used as a pre-filter before NDVI analysis: sites with standing water are
excluded from vegetation change analysis to avoid false ghost-project signals.

Formula: NDWI = (B03 − B08) / (B03 + B08)

A mean NDWI > 0.3 indicates open water presence; the NDVI pipeline will skip
such scenes rather than misinterpreting water reflectance as low vegetation.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import rasterio
from loguru import logger

from src.config import config
from src.utils import calculate_ndwi, extract_statistics, ensure_directory


@dataclass
class NDWIResult:
    """Result of a single NDWI analysis pass."""

    scene_id: str
    ndwi_mean: float
    ndwi_std: float
    water_present: bool
    acquisition_date: Optional[str] = None
    processed_date: Optional[str] = None


class NDWIProcessor:
    """
    Process Sentinel-2 imagery to compute NDWI and flag water-covered sites.

    Uses Green (B03) and Near-Infrared (B08) bands at 10 m resolution.
    Any scene with mean NDWI > config.NDWI_WATER_THRESHOLD (default 0.3) is
    marked `water_present = True` and should be excluded from NDVI analysis.
    """

    def __init__(self, scene_path: Path):
        if not scene_path.exists():
            raise FileNotFoundError(f"Scene not found: {scene_path}")
        if not scene_path.name.endswith(".SAFE"):
            raise ValueError(f"Expected a .SAFE directory, got: {scene_path}")
        self.scene_path = scene_path
        self.scene_id = scene_path.stem

    # ------------------------------------------------------------------
    # Band loading
    # ------------------------------------------------------------------

    def load_bands_rasterio(self) -> tuple[np.ndarray, np.ndarray, dict]:
        """Load Green (B03) and NIR (B08) bands at 10 m resolution."""
        granule_dir = self.scene_path / "GRANULE"
        granules = list(granule_dir.iterdir())
        img_data_dir = granules[0] / "IMG_DATA" / "R10m"

        b03_files = list(img_data_dir.glob("*B03_10m.jp2"))
        b08_files = list(img_data_dir.glob("*B08_10m.jp2"))

        if not b03_files or not b08_files:
            raise FileNotFoundError(
                f"B03 or B08 band files not found in {img_data_dir}"
            )

        with rasterio.open(b03_files[0]) as src:
            green = src.read(1).astype(np.float32)
            transform = src.transform
            crs = src.crs
            profile = src.profile

        with rasterio.open(b08_files[0]) as src:
            nir = src.read(1).astype(np.float32)

        return green, nir, {"crs": crs, "transform": transform, "profile": profile}

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    def compute_ndwi(self, green: np.ndarray, nir: np.ndarray) -> np.ndarray:
        """Compute pixel-wise NDWI; result clipped to [-1, 1]."""
        return calculate_ndwi(green, nir)

    def classify_water(self, ndwi: np.ndarray) -> NDWIResult:
        """
        Derive statistics and classify water presence.

        Returns NDWIResult with water_present=True when ndwi_mean > threshold.
        """
        stats = extract_statistics(ndwi)
        ndwi_mean = stats["mean"] if np.isfinite(stats["mean"]) else 0.0
        ndwi_std = stats["std"] if np.isfinite(stats["std"]) else 0.0

        return NDWIResult(
            scene_id=self.scene_id,
            ndwi_mean=ndwi_mean,
            ndwi_std=ndwi_std,
            water_present=ndwi_mean > config.NDWI_WATER_THRESHOLD,
            processed_date=datetime.now().isoformat(),
        )

    # ------------------------------------------------------------------
    # Public processing entry point
    # ------------------------------------------------------------------

    def process(self) -> NDWIResult:
        """
        Full NDWI processing workflow: load bands → compute index → classify.

        Returns an NDWIResult.  Does NOT write any output files; NDWI is
        used only as a gate for the downstream NDVI pipeline.
        """
        logger.info("Computing NDWI for scene: %s", self.scene_id)

        green, nir, _metadata = self.load_bands_rasterio()
        ndwi = self.compute_ndwi(green, nir)
        result = self.classify_water(ndwi)

        if result.water_present:
            logger.info(
                "Water detected (NDWI mean=%.3f > %.1f) — skipping NDVI for %s",
                result.ndwi_mean,
                config.NDWI_WATER_THRESHOLD,
                self.scene_id,
            )
        else:
            logger.info(
                "No standing water (NDWI mean=%.3f) — NDVI analysis can proceed for %s",
                result.ndwi_mean,
                self.scene_id,
            )

        return result
