"""
Configuration management for satellite processing.

Loads environment variables and provides configuration access throughout the module.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """
    Centralized configuration for satellite data processing.
    """

    # ========================================================================
    # Paths
    # ========================================================================
    PROJECT_ROOT = Path(__file__).parent.parent
    DATA_ROOT = PROJECT_ROOT / "data"
    RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", DATA_ROOT / "raw"))
    PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", DATA_ROOT / "processed"))
    TRAINING_DATA_DIR = Path(os.getenv("TRAINING_DATA_DIR", DATA_ROOT / "training"))

    # Ensure directories exist
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    TRAINING_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # Copernicus Data Space
    # ========================================================================
    COPERNICUS_USERNAME: Optional[str] = os.getenv("COPERNICUS_USERNAME")
    COPERNICUS_PASSWORD: Optional[str] = os.getenv("COPERNICUS_PASSWORD")
    COPERNICUS_CLIENT_ID: Optional[str] = os.getenv("COPERNICUS_CLIENT_ID")
    COPERNICUS_CLIENT_SECRET: Optional[str] = os.getenv("COPERNICUS_CLIENT_SECRET")

    # Copernicus API endpoints
    COPERNICUS_API_URL = (
        "https://catalogue.dataspace.copernicus.eu/resto/api/collections"
    )
    COPERNICUS_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

    # ========================================================================
    # AWS Configuration
    # ========================================================================
    # Use `or None` so that a blank env var (AWS_ACCESS_KEY_ID=) is stored as
    # None, not "". boto3's StaticProvider skips None and falls through to the
    # credential chain (env vars → ~/.aws/credentials → IAM role). An explicit
    # empty string would behave inconsistently across boto3 versions.
    AWS_ACCESS_KEY_ID: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID") or None
    AWS_SECRET_ACCESS_KEY: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY") or None
    # None → boto3 reads region from ~/.aws/config; only falls back to
    # "us-east-1" if no region is configured anywhere in the chain.
    AWS_REGION: Optional[str] = os.getenv("AWS_REGION") or None
    S3_BUCKET: str = os.getenv("S3_BUCKET", "oneka-satellite-data")

    # ========================================================================
    # Processing Parameters
    # ========================================================================
    SNAP_INSTALL_DIR: Path = Path(os.getenv("SNAP_INSTALL_DIR", "/usr/local/snap"))
    NUM_WORKERS: int = int(os.getenv("NUM_WORKERS", "4"))
    MAX_CLOUD_COVER: int = int(os.getenv("MAX_CLOUD_COVER", "20"))

    # Sentinel-2 bands
    SENTINEL2_BANDS = {
        "B01": "Coastal aerosol",
        "B02": "Blue",
        "B03": "Green",
        "B04": "Red",
        "B05": "Red Edge 1",
        "B06": "Red Edge 2",
        "B07": "Red Edge 3",
        "B08": "NIR",
        "B8A": "NIR narrow",
        "B09": "Water vapor",
        "B10": "SWIR - Cirrus",
        "B11": "SWIR 1",
        "B12": "SWIR 2",
    }

    # Sentinel-1 polarizations
    SENTINEL1_POLARIZATIONS = ["VV", "VH", "HH", "HV"]

    # ========================================================================
    # Analysis Parameters
    # ========================================================================

    # NDVI thresholds
    NDVI_CLEARING_THRESHOLD = 0.15  # Minimum drop to detect clearing
    NDVI_HEALTHY_VEGETATION = 0.3  # Threshold for healthy vegetation
    NDVI_RECOVERY_THRESHOLD = 0.5  # Recovery ratio indicating abandonment

    # SAR backscatter thresholds (dB)
    SAR_STRUCTURE_THRESHOLD = 3.0  # dB increase indicating new structures
    SAR_VV_TYPICAL_RANGE = (-25, 5)  # Typical VV backscatter range
    SAR_VH_TYPICAL_RANGE = (-30, 0)  # Typical VH backscatter range

    # NDWI thresholds
    NDWI_WATER_THRESHOLD = 0.3  # Threshold indicating water presence

    # Area of Interest (AOI) radius in meters
    AOI_RADIUS = 500  # 500m radius around project coordinates

    # ========================================================================
    # Backend API Integration
    # ========================================================================
    BACKEND_API_URL: str = os.getenv("BACKEND_API_URL", "http://localhost:8000")
    BACKEND_API_KEY: Optional[str] = os.getenv("BACKEND_API_KEY")

    # ========================================================================
    # Logging
    # ========================================================================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: Path = Path(os.getenv("LOG_FILE", "logs/satellite_processing.log"))

    # Create logs directory
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # Development
    # ========================================================================
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    TEST_MODE: bool = os.getenv("TEST_MODE", "False").lower() == "true"

    @classmethod
    def validate(cls) -> bool:
        """
        Validate that required configuration is present.

        Returns:
            bool: True if configuration is valid
        """
        errors = []

        if not cls.COPERNICUS_USERNAME:
            errors.append("COPERNICUS_USERNAME not set")

        if not cls.COPERNICUS_PASSWORD:
            errors.append("COPERNICUS_PASSWORD not set")

        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            return False

        return True

    @classmethod
    def print_config(cls) -> None:
        """
        Print current configuration (masking sensitive data).
        """
        print("=" * 70)
        print("ONEKA AI - Satellite Processing Configuration")
        print("=" * 70)
        print(f"Project Root: {cls.PROJECT_ROOT}")
        print(f"Raw Data Dir: {cls.RAW_DATA_DIR}")
        print(f"Processed Data Dir: {cls.PROCESSED_DATA_DIR}")
        print(f"Training Data Dir: {cls.TRAINING_DATA_DIR}")
        print(f"Copernicus User: {cls.COPERNICUS_USERNAME or 'NOT SET'}")
        print(f"Max Cloud Cover: {cls.MAX_CLOUD_COVER}%")
        print(f"AOI Radius: {cls.AOI_RADIUS}m")
        print(f"Workers: {cls.NUM_WORKERS}")
        print(f"Debug Mode: {cls.DEBUG}")
        print(f"Backend API: {cls.BACKEND_API_URL}")
        print("=" * 70)


# Create singleton config instance
config = Config()

# Validate configuration on import (only warn, don't fail)
if not config.validate():
    print("⚠️  Warning: Copernicus credentials not configured")
    print("   Copy .env.example to .env and add your credentials")
