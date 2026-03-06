"""
Application configuration and settings management using Pydantic.
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional

# Absolute path to repo root (backend/src/config.py → parents[2] = oneka/)
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    # Application
    app_name: str = "ONEKA AI API"
    debug: bool = False
    environment: str = "development"
    api_version: str = "1.0.0"

    # Database
    database_url: str
    database_test_url: Optional[str] = None

    # API Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Security
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # AWS Configuration
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-east-1"
    aws_s3_bucket: Optional[str] = None

    # External APIs
    copernicus_username: Optional[str] = None
    copernicus_password: Optional[str] = None
    google_maps_api_key: Optional[str] = None

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Data Sources
    ppip_base_url: str = "https://tenders.go.ke"
    kmhfl_api_url: str = "https://api.kmhfr.health.go.ke/api"

    # ML Model (Phase 4)
    # Default resolves to satellite/models/ghost_detector_v1.pkl from repo root.
    # Override via ML_MODEL_PATH env var if the model is stored elsewhere.
    ml_model_path: str = str(_REPO_ROOT / "satellite" / "models" / "ghost_detector_v1.pkl")

    # Phase 5 — Tiles & Google Maps
    tile_s3_prefix: str = "tiles"
    tile_generation_timeout: int = 600  # seconds
    tile_cache_ttl: int = 604800  # 7 days in seconds
    redis_tile_cache_enabled: bool = True

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
