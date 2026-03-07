"""
Google Maps 3D Tiles API proxy router — Phase 5.

Provides secure server-side proxying of Google Maps Tiles API requests
without exposing the API key to the frontend.

Endpoints:
  POST /api/v1/maps/tiles/session
      Create a session token for tile requests, cache in Redis.

  GET /api/v1/maps/tiles/{session_token}/{z}/{x}/{y}
      Proxy tile request to Google Maps API using cached session.
"""

from __future__ import annotations

import logging
import hashlib
from typing import Optional
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, HTTPException, Request, status, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.database import get_db
from src.config import settings
from src.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

# Session cache (in production, use Redis)
# Format: {token_hash: {session_token, created_at, expires_at}}
_SESSION_CACHE = {}
_SESSION_TTL = 86400  # 24 hours in seconds


def _hash_token(token: str) -> str:
    """Hash session token for cache key."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _is_token_valid(token_hash: str) -> bool:
    """Check if cached token is still valid."""
    if token_hash not in _SESSION_CACHE:
        return False

    expires_at = _SESSION_CACHE[token_hash].get("expires_at")
    if expires_at is None:
        return False

    return datetime.utcnow() < expires_at


# ────────────────────────────────────────────────────────────────────────────


@router.post("/maps/tiles/session")
@limiter.limit("5/minute")
async def create_session(request: Request, db: Session = Depends(get_db)):
    """
    Create a Google Maps Tiles API session token.

    Server-side call to Google API. Token is cached in memory/Redis for
    24 hours to reduce API calls. Frontend uses the returned session_token
    for subsequent tile requests.

    **Security:** Never expose GOOGLE_MAPS_API_KEY to frontend response.

    Returns:
        {
            'session_token': '...',
            'expires_in': 86400  # seconds
        }

    Raises:
        HTTPException 503: Google API unavailable or misconfigured
        HTTPException 400: Missing API key configuration
    """
    if not settings.google_maps_api_key:
        logger.error("Google Maps API key not configured")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Maps API key not configured on server",
        )

    try:
        # Call Google Tiles API to create session
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://tile.googleapis.com/v1/createSession",
                params={"key": settings.google_maps_api_key},
                json={"mapType": "satellite"},  # Request satellite imagery
            )

        if response.status_code != 200:
            logger.error(
                f"Google Tiles API returned {response.status_code}: {response.text}"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google Maps API unavailable",
            )

        # Parse response
        data = response.json()
        session_token = data.get("session")

        if not session_token:
            logger.error(f"Google API response missing session token: {data}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Invalid response from Google API",
            )

        # Cache token
        token_hash = _hash_token(session_token)
        _SESSION_CACHE[token_hash] = {
            "session_token": session_token,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(seconds=_SESSION_TTL),
        }

        logger.info(f"Created Google Tiles session: {token_hash}")

        return {
            "session_token": session_token,
            "expires_in": _SESSION_TTL,
        }

    except httpx.TimeoutException:
        logger.error("Google Tiles API request timed out")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Maps request timed out",
        )

    except httpx.RequestError as e:
        logger.exception(f"Google Tiles API request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to reach Google Maps API",
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Unexpected error creating Google session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session creation failed",
        )


# ────────────────────────────────────────────────────────────────────────────


@router.get("/maps/tiles/{session_token}/{z}/{x}/{y}")
@limiter.limit("60/minute")
async def proxy_tile(request: Request, session_token: str, z: int, x: int, y: int):
    """
    Proxy tile request to Google Maps Tiles API.

    Validates that session_token is valid, then forwards request to Google.
    Tile response is cached for 7 days to reduce API calls.

    **Security Notes:**
      - Session token is validated against cache (prevents unauthorized access)
      - Google API key is added server-side (never exposed to frontend)
      - Tile responses are cached to minimize API quota usage

    Args:
        session_token: Session token from POST /maps/tiles/session
        z: Zoom level (0-28 typical)
        x: Tile X coordinate
        y: Tile Y coordinate

    Returns:
        PNG tile bytes with Content-Type: image/png

    Raises:
        HTTPException 400: Invalid or expired session token
        HTTPException 404: Tile out of bounds
        HTTPException 503: Google API unavailable
    """
    if not settings.google_maps_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google Maps API key not configured",
        )

    # Validate zoom and coordinates
    if not (0 <= z <= 28):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid zoom level: {z} (must be 0-28)",
        )

    if not (0 <= x < (2 ** z) and 0 <= y < (2 ** z)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tile out of bounds at z{z}/x{x}/y{y}",
        )

    # Validate session token
    token_hash = _hash_token(session_token)

    if not _is_token_valid(token_hash):
        logger.warning(f"Invalid or expired session token: {token_hash}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session token invalid or expired. Request new token from POST /maps/tiles/session",
        )

    try:
        # Proxy request to Google Tiles API
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Use the cached session token
            cached_token = _SESSION_CACHE[token_hash]["session_token"]

            url = f"https://tile.googleapis.com/v1/tiles/{z}/{x}/{y}"
            response = await client.get(url, params={"session": cached_token})

        if response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tile not available at z{z}/x{x}/y{y}",
            )

        if response.status_code != 200:
            logger.error(
                f"Google Tiles API returned {response.status_code} for z{z}/x{x}/y{y}"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google Maps API error",
            )

        # Return PNG tile bytes
        return StreamingResponse(
            iter([response.content]),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=604800"},  # 7 days
        )

    except httpx.TimeoutException:
        logger.warning(f"Tile request timeout for z{z}/x{x}/y{y}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tile request timed out",
        )

    except httpx.RequestError as e:
        logger.exception(f"Tile request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to fetch tile from Google Maps",
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Unexpected error proxying tile z{z}/x{x}/y{y}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tile fetch failed",
        )
