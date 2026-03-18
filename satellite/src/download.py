"""
Copernicus Data Space API client for downloading Sentinel-1 and Sentinel-2 imagery.

Uses OAuth2 Bearer-token authentication against the CDSE OData API.
SentinelAPI (basic auth) was dropped because the CDSE catalogue requires
OAuth2 since early 2024.

Auth flow:
  POST  https://identity.dataspace.copernicus.eu/…/token  → access_token (10 min TTL)
  GET   https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter=…  → scene list
  GET   https://zipper.dataspace.copernicus.eu/odata/v1/Products({id})/$value   → zip stream
"""

import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
from loguru import logger

from src.config import config
from src.utils import (
    parse_coordinates,
    create_bbox,
    validate_date_range,
    format_file_size,
    ensure_directory,
)

# CDSE OData endpoints
_CATALOGUE = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
_ZIPPER = "https://zipper.dataspace.copernicus.eu/odata/v1/Products"

# OAuth2 client for public CDSE access
_CLIENT_ID = "cdse-public"


class CopernicusDownloader:
    """
    Client for downloading Sentinel satellite imagery from Copernicus Data Space.

    Supports two OAuth2 auth flows (auto-detected from .env):
      1. client_credentials — preferred; uses COPERNICUS_CLIENT_ID + CLIENT_SECRET
      2. password (ROPC)    — fallback; uses COPERNICUS_USERNAME + PASSWORD
    The access token is cached and automatically refreshed before expiry.
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.username = username or config.COPERNICUS_USERNAME
        self.password = password or config.COPERNICUS_PASSWORD
        self._client_id = config.COPERNICUS_CLIENT_ID
        self._client_secret = config.COPERNICUS_CLIENT_SECRET

        # Require at least one auth method
        has_client_creds = bool(self._client_id and self._client_secret)
        has_password = bool(self.username and self.password)
        if not has_client_creds and not has_password:
            raise ValueError(
                "No Copernicus credentials found. Set either "
                "COPERNICUS_CLIENT_ID + COPERNICUS_CLIENT_SECRET "
                "or COPERNICUS_USERNAME + COPERNICUS_PASSWORD in .env"
            )

        self._use_client_creds = has_client_creds

        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._refresh_token()

        logger.info("Copernicus API client initialized")

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _refresh_token(self) -> None:
        """Fetch a new OAuth2 access token and cache its expiry time.

        Tries client_credentials grant first when a dedicated OAuth client is
        configured; falls back to resource-owner password grant if it fails or
        if no client credentials are set.
        """
        if self._use_client_creds:
            payload = {
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
            resp = requests.post(config.COPERNICUS_TOKEN_URL, data=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                self._token = data["access_token"]
                self._token_expires_at = time.time() + data.get("expires_in", 600) - 60
                return
            # client_credentials rejected — try password grant as fallback
            logger.warning(
                "client_credentials grant failed (%s) — falling back to password grant",
                resp.status_code,
            )
            if not (self.username and self.password):
                resp.raise_for_status()  # no fallback available; surface the error

        payload = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
            "client_id": _CLIENT_ID,
        }
        resp = requests.post(config.COPERNICUS_TOKEN_URL, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 600) - 60

    def _auth_headers(self) -> Dict[str, str]:
        """Return Authorization header, refreshing the token if near expiry."""
        if time.time() >= self._token_expires_at:
            self._refresh_token()
        return {"Authorization": f"Bearer {self._token}"}

    # ── Search ────────────────────────────────────────────────────────────────

    def search_sentinel2(
        self,
        lat: float,
        lon: float,
        start_date: str,
        end_date: str,
        max_cloud_cover: int = 20,
        product_type: str = "S2MSI2A",
    ) -> List[Dict]:
        """
        Search for Sentinel-2 scenes via the CDSE OData API.

        Args:
            lat: Centre latitude.
            lon: Centre longitude.
            start_date: Search window start (YYYY-MM-DD).
            end_date: Search window end (YYYY-MM-DD).
            max_cloud_cover: Maximum cloud cover percentage (0-100).
            product_type: Sentinel-2 product type (default S2MSI2A = Level-2A).

        Returns:
            List of scene metadata dicts, sorted most-recent first.
        """
        logger.info(f"Searching Sentinel-2 scenes for ({lat}, {lon})")
        logger.info(f"Date range: {start_date} to {end_date}, max cloud: {max_cloud_cover}%")

        parse_coordinates(lat, lon)
        start_dt, end_dt = validate_date_range(start_date, end_date)

        bbox = create_bbox(lat, lon, radius_m=config.AOI_RADIUS)
        footprint = (
            f"POLYGON(({bbox[0]} {bbox[1]}, {bbox[2]} {bbox[1]}, "
            f"{bbox[2]} {bbox[3]}, {bbox[0]} {bbox[3]}, {bbox[0]} {bbox[1]}))"
        )

        odata_filter = (
            f"Collection/Name eq 'SENTINEL-2' and "
            f"Attributes/OData.CSC.StringAttribute/any("
            f"  att:att/Name eq 'productType' and "
            f"  att/OData.CSC.StringAttribute/Value eq '{product_type}') and "
            f"Attributes/OData.CSC.DoubleAttribute/any("
            f"  att:att/Name eq 'cloudCover' and "
            f"  att/OData.CSC.DoubleAttribute/Value le {float(max_cloud_cover)}) and "
            f"ContentDate/Start gt {start_dt.strftime('%Y-%m-%dT00:00:00.000Z')} and "
            f"ContentDate/Start lt {end_dt.strftime('%Y-%m-%dT23:59:59.000Z')} and "
            f"OData.CSC.Intersects(area=geography'SRID=4326;{footprint}')"
        )

        try:
            resp = requests.get(
                _CATALOGUE,
                params={
                    "$filter": odata_filter,
                    "$orderby": "ContentDate/Start desc",
                    "$top": 10,
                    "$expand": "Attributes",
                },
                headers=self._auth_headers(),
                timeout=60,
            )
            resp.raise_for_status()
            products = resp.json().get("value", [])
            logger.info(f"Found {len(products)} Sentinel-2 scenes")
            return [self._normalise_s2(p) for p in products]

        except Exception as exc:
            logger.error(f"Sentinel-2 search failed: {exc}")
            return []

    def search_sentinel1(
        self,
        lat: float,
        lon: float,
        start_date: str,
        end_date: str,
        product_type: str = "GRD",
        polarization: str = "VV VH",
    ) -> List[Dict]:
        """
        Search for Sentinel-1 SAR scenes via the CDSE OData API.

        Args:
            lat: Centre latitude.
            lon: Centre longitude.
            start_date: Search window start (YYYY-MM-DD).
            end_date: Search window end (YYYY-MM-DD).
            product_type: Product type (GRD or SLC).
            polarization: Ignored (filter removed for broader coverage).

        Returns:
            List of scene metadata dicts, sorted most-recent first.
        """
        logger.info(f"Searching Sentinel-1 scenes for ({lat}, {lon})")

        parse_coordinates(lat, lon)
        start_dt, end_dt = validate_date_range(start_date, end_date)

        bbox = create_bbox(lat, lon, radius_m=config.AOI_RADIUS)
        footprint = (
            f"POLYGON(({bbox[0]} {bbox[1]}, {bbox[2]} {bbox[1]}, "
            f"{bbox[2]} {bbox[3]}, {bbox[0]} {bbox[3]}, {bbox[0]} {bbox[1]}))"
        )

        odata_filter = (
            f"Collection/Name eq 'SENTINEL-1' and "
            f"Attributes/OData.CSC.StringAttribute/any("
            f"  att:att/Name eq 'productType' and "
            f"  att/OData.CSC.StringAttribute/Value eq '{product_type}') and "
            f"ContentDate/Start gt {start_dt.strftime('%Y-%m-%dT00:00:00.000Z')} and "
            f"ContentDate/Start lt {end_dt.strftime('%Y-%m-%dT23:59:59.000Z')} and "
            f"OData.CSC.Intersects(area=geography'SRID=4326;{footprint}')"
        )

        try:
            resp = requests.get(
                _CATALOGUE,
                params={
                    "$filter": odata_filter,
                    "$orderby": "ContentDate/Start desc",
                    "$top": 5,
                    "$expand": "Attributes",
                },
                headers=self._auth_headers(),
                timeout=60,
            )
            resp.raise_for_status()
            products = resp.json().get("value", [])
            logger.info(f"Found {len(products)} Sentinel-1 scenes")
            return [self._normalise_s1(p) for p in products]

        except Exception as exc:
            logger.error(f"Sentinel-1 search failed: {exc}")
            return []

    # ── Download ──────────────────────────────────────────────────────────────

    def download_scene(
        self,
        uuid: str,
        output_dir: Path,
        unzip: bool = True,
    ) -> Optional[Path]:
        """
        Download a satellite scene by its CDSE product UUID.

        Args:
            uuid: CDSE product UUID from search results.
            output_dir: Destination directory.
            unzip: Unzip the downloaded SAFE zip archive.

        Returns:
            Path to the SAFE directory (if unzip=True) or zip file, or None on failure.
        """
        logger.info(f"Downloading scene: {uuid}")
        ensure_directory(output_dir)

        zip_dest = output_dir / f"{uuid}.zip"

        try:
            # CDSE zipper streams the SAFE archive as a zip
            download_url = f"{_ZIPPER}({uuid})/$value"
            with requests.get(
                download_url,
                headers=self._auth_headers(),
                stream=True,
                allow_redirects=True,
                timeout=600,
            ) as resp:
                resp.raise_for_status()

                total = int(resp.headers.get("content-length", 0))
                received = 0
                with open(zip_dest, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                        fh.write(chunk)
                        received += len(chunk)

            logger.info(f"Downloaded: {zip_dest.name} ({format_file_size(received)})")

            if not unzip:
                return zip_dest

            logger.info("Extracting SAFE archive…")
            with zipfile.ZipFile(zip_dest, "r") as zf:
                zf.extractall(output_dir)

            # The SAFE directory shares its stem with the zip
            safe_candidates = list(output_dir.glob("*.SAFE"))
            if safe_candidates:
                safe_dir = safe_candidates[0]
                logger.info(f"Extracted to: {safe_dir.name}")
                return safe_dir

            logger.warning("SAFE directory not found after extraction")
            return zip_dest

        except Exception as exc:
            logger.error(f"Download failed for {uuid}: {exc}")
            return None

    def download_multiple(
        self,
        scenes: List[Dict],
        output_dir: Path,
        max_scenes: int = 5,
    ) -> List[Path]:
        """Download multiple scenes, stopping at max_scenes."""
        downloaded = []
        for i, scene in enumerate(scenes[:max_scenes]):
            logger.info(f"Downloading scene {i+1}/{min(len(scenes), max_scenes)}: {scene['title']}")
            path = self.download_scene(scene["uuid"], output_dir, unzip=True)
            if path:
                downloaded.append(path)
        logger.info(f"Downloaded {len(downloaded)}/{min(len(scenes), max_scenes)} scenes")
        return downloaded

    # ── Internal normalisation ────────────────────────────────────────────────

    @staticmethod
    def _attr(product: Dict, name: str, default=None):
        """Pull a named attribute value from an OData product's Attributes list."""
        for attr in product.get("Attributes", []):
            if attr.get("Name") == name:
                return attr.get("Value", default)
        return default

    def _normalise_s2(self, product: Dict) -> Dict:
        sensing_date = product.get("ContentDate", {}).get("Start", "")[:10]
        return {
            "uuid": product["Id"],
            "title": product["Name"],
            "sensing_date": sensing_date,
            "cloud_cover": self._attr(product, "cloudCover", 0),
            "size_mb": str(round(product.get("ContentLength", 0) / 1e6, 1)),
            "product_type": self._attr(product, "productType", "S2MSI2A"),
        }

    def _normalise_s1(self, product: Dict) -> Dict:
        sensing_date = product.get("ContentDate", {}).get("Start", "")[:10]
        return {
            "uuid": product["Id"],
            "title": product["Name"],
            "sensing_date": sensing_date,
            "polarization": self._attr(product, "polarisationChannels", "N/A"),
            "size_mb": str(round(product.get("ContentLength", 0) / 1e6, 1)),
            "product_type": self._attr(product, "productType", "GRD"),
        }


def main():
    """CLI wrapper for ad-hoc scene searches and downloads."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Download Sentinel satellite imagery from Copernicus Data Space"
    )
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--start-date", type=str, required=True)
    parser.add_argument("--end-date", type=str, required=True)
    parser.add_argument("--sensor", choices=["sentinel-1", "sentinel-2"], default="sentinel-2")
    parser.add_argument("--max-cloud", type=int, default=20)
    parser.add_argument("--max-scenes", type=int, default=5)
    parser.add_argument("--output", type=str, default=None)

    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else config.RAW_DATA_DIR / f"{args.sensor}_{args.start_date}"

    downloader = CopernicusDownloader()

    if args.sensor == "sentinel-2":
        scenes = downloader.search_sentinel2(args.lat, args.lon, args.start_date, args.end_date, args.max_cloud)
    else:
        scenes = downloader.search_sentinel1(args.lat, args.lon, args.start_date, args.end_date)

    if not scenes:
        logger.error("No scenes found matching criteria")
        return

    logger.info(f"Found {len(scenes)} scenes")
    downloader.download_multiple(scenes, output_dir, args.max_scenes)


if __name__ == "__main__":
    from src.utils import setup_logger
    setup_logger(level=config.LOG_LEVEL)
    main()
