"""
Phase 7 — Google Maps proxy router tests.

Covers src/routers/maps.py with mocked httpx and session cache.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _seed_session_cache(token: str = "test-session-token"):
    """Inject a valid session into the maps router cache."""
    from src.routers.maps import _SESSION_CACHE, _hash_token
    token_hash = _hash_token(token)
    _SESSION_CACHE[token_hash] = {
        "session_token": token,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(hours=1),
    }
    return token


def _clear_session_cache():
    from src.routers.maps import _SESSION_CACHE
    _SESSION_CACHE.clear()


# =============================================================================
# Session cache helpers
# =============================================================================


class TestSessionHelpers:
    """Tests for _hash_token and _is_token_valid."""

    def test_hash_token_deterministic(self):
        from src.routers.maps import _hash_token
        assert _hash_token("abc") == _hash_token("abc")
        assert _hash_token("abc") != _hash_token("xyz")

    def test_is_token_valid_expired(self):
        from src.routers.maps import _SESSION_CACHE, _hash_token, _is_token_valid
        _clear_session_cache()
        token_hash = _hash_token("expired-token")
        _SESSION_CACHE[token_hash] = {
            "session_token": "expired-token",
            "created_at": datetime.utcnow() - timedelta(hours=25),
            "expires_at": datetime.utcnow() - timedelta(hours=1),
        }
        assert _is_token_valid(token_hash) is False
        _clear_session_cache()

    def test_is_token_valid_missing(self):
        from src.routers.maps import _is_token_valid
        _clear_session_cache()
        assert _is_token_valid("nonexistent_hash") is False


# =============================================================================
# proxy_tile success path
# =============================================================================


class TestProxyTileSuccess:
    """Tests for the proxy_tile happy path."""

    def test_proxy_tile_returns_png(self, client):
        """Valid session + valid tile => 200 with image/png."""
        _clear_session_cache()
        token = _seed_session_cache()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        with patch("src.routers.maps.settings") as mock_settings:
            mock_settings.google_maps_api_key = "test-key"
            with patch("src.routers.maps.httpx.AsyncClient") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.get.return_value = mock_response
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client_instance

                resp = client.get(f"/api/v1/maps/tiles/{token}/10/512/512")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        _clear_session_cache()

    def test_proxy_tile_google_404(self, client):
        """Google returns 404 for tile => 404."""
        _clear_session_cache()
        token = _seed_session_cache()

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("src.routers.maps.settings") as mock_settings:
            mock_settings.google_maps_api_key = "test-key"
            with patch("src.routers.maps.httpx.AsyncClient") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.get.return_value = mock_response
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client_instance

                resp = client.get(f"/api/v1/maps/tiles/{token}/10/512/512")

        assert resp.status_code == 404
        _clear_session_cache()


# =============================================================================
# proxy_tile error paths
# =============================================================================


class TestProxyTileErrors:
    """Tests for proxy_tile error handling."""

    def test_proxy_tile_expired_token(self, client):
        """Expired session token => 400."""
        from src.routers.maps import _SESSION_CACHE, _hash_token
        _clear_session_cache()
        token = "expired-token"
        token_hash = _hash_token(token)
        _SESSION_CACHE[token_hash] = {
            "session_token": token,
            "created_at": datetime.utcnow() - timedelta(hours=25),
            "expires_at": datetime.utcnow() - timedelta(hours=1),
        }

        with patch("src.routers.maps.settings") as mock_settings:
            mock_settings.google_maps_api_key = "test-key"
            resp = client.get(f"/api/v1/maps/tiles/{token}/10/512/512")

        assert resp.status_code == 400
        _clear_session_cache()

    def test_proxy_tile_no_api_key(self, client):
        """Missing API key => 500."""
        _clear_session_cache()
        with patch("src.routers.maps.settings") as mock_settings:
            mock_settings.google_maps_api_key = None
            resp = client.get("/api/v1/maps/tiles/any-token/10/0/0")

        assert resp.status_code == 500
        _clear_session_cache()
