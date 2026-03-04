"""
Application configuration and settings management using Pydantic.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    # Application
    app_name: str = "ONEKA AI API"
    debug: bool = True
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

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
