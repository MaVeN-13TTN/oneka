"""
Phase 7 — Security hardening tests.

Validates security headers, rate limiting, coordinate validation,
input sanitization, config defaults, and presigned URL cap.
"""

from __future__ import annotations

from uuid import uuid4
from unittest.mock import patch, MagicMock

import pytest


# =============================================================================
# Security headers
# =============================================================================


class TestSecurityHeaders:
    """All responses must include hardened security headers."""

    def test_x_content_type_options(self, client):
        resp = client.get("/")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options(self, client):
        resp = client.get("/")
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_x_xss_protection(self, client):
        resp = client.get("/")
        assert resp.headers.get("x-xss-protection") == "1; mode=block"

    def test_referrer_policy(self, client):
        resp = client.get("/")
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_content_security_policy(self, client):
        resp = client.get("/")
        csp = resp.headers.get("content-security-policy")
        assert csp is not None
        assert "default-src 'self'" in csp

    def test_hsts(self, client):
        resp = client.get("/")
        hsts = resp.headers.get("strict-transport-security")
        assert hsts is not None
        assert "max-age=" in hsts


# =============================================================================
# Coordinate validation on satellite tiles
# =============================================================================


class TestCoordinateValidation:
    """Satellite tile endpoint rejects invalid coordinates."""

    def test_satellite_tile_invalid_zoom(self, client):
        resp = client.get(f"/api/v1/satellite/tiles/{uuid4()}/ndvi/999/0/0")
        assert resp.status_code == 400
        assert "zoom" in resp.json()["detail"].lower()

    def test_satellite_tile_negative_zoom(self, client):
        resp = client.get(f"/api/v1/satellite/tiles/{uuid4()}/ndvi/-1/0/0")
        assert resp.status_code == 400

    def test_satellite_tile_x_out_of_bounds(self, client):
        # z=8 -> max x = 255 (2^8 - 1)
        resp = client.get(f"/api/v1/satellite/tiles/{uuid4()}/ndvi/8/999/0")
        assert resp.status_code == 400
        assert "bounds" in resp.json()["detail"].lower()


# =============================================================================
# Input sanitization
# =============================================================================


class TestInputSanitization:
    """String query params are sanitized in projects router."""

    def test_county_filter_strips_control_chars(self, client):
        """Control characters in county param don't cause errors."""
        resp = client.get("/api/v1/projects", params={"county": "\x00Nairobi\x01"})
        assert resp.status_code == 200

    def test_county_filter_long_input_truncated(self, client):
        """Very long county string is handled without error."""
        long_county = "A" * 500
        resp = client.get("/api/v1/projects", params={"county": long_county})
        assert resp.status_code == 200

    def test_sanitize_input_function(self):
        """Direct test of _sanitize_input helper."""
        from src.routers.projects import _sanitize_input
        assert _sanitize_input("\x00\x01hello\x7f") == "hello"
        assert _sanitize_input("  multiple   spaces  ") == "multiple spaces"
        assert len(_sanitize_input("x" * 500, max_length=200)) == 200


# =============================================================================
# Debug default
# =============================================================================


class TestDebugDefault:
    """Config defaults are production-safe."""

    def test_default_debug_is_false(self):
        """Settings.debug defaults to False (production-safe)."""
        from pydantic_settings import BaseSettings
        from src.config import Settings

        # Check the model field default
        field = Settings.model_fields["debug"]
        assert field.default is False


# =============================================================================
# Presigned URL cap
# =============================================================================


class TestPresignedUrlCap:
    """S3 presigned URLs are capped at 3600 seconds."""

    def test_s3_presigned_url_capped(self):
        """get_pdf_url caps expiration at 3600."""
        from src.services.s3_storage import S3StorageService
        with patch("src.services.s3_storage.boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_s3.generate_presigned_url.return_value = "https://url"
            mock_boto.return_value = mock_s3
            svc = S3StorageService()
            svc.bucket_name = "test-bucket"

        svc.get_pdf_url("key.pdf", expiration=7200)

        call_kwargs = mock_s3.generate_presigned_url.call_args
        # ExpiresIn should be 3600, not 7200
        expires_in = call_kwargs[1].get("ExpiresIn") or call_kwargs[0][-1]
        assert expires_in == 3600
