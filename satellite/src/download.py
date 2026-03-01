"""
Copernicus Data Space API client for downloading Sentinel-1 and Sentinel-2 imagery.

This module handles authentication and download of satellite scenes from the
Copernicus Data Space Ecosystem.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from loguru import logger
from sentinelsat import SentinelAPI, read_geojson, geojson_to_wkt
from tqdm import tqdm

from src.config import config
from src.utils import (
    parse_coordinates,
    create_bbox,
    validate_date_range,
    format_file_size,
    ensure_directory,
)


class CopernicusDownloader:
    """
    Client for downloading Sentinel satellite imagery from Copernicus Data Space.
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize Copernicus downloader.

        Args:
            username: Copernicus Data Space username
            password: Copernicus Data Space password
        """
        self.username = username or config.COPERNICUS_USERNAME
        self.password = password or config.COPERNICUS_PASSWORD

        if not self.username or not self.password:
            raise ValueError(
                "Copernicus credentials not provided. "
                "Set COPERNICUS_USERNAME and COPERNICUS_PASSWORD in .env"
            )

        # Initialize SentinelAPI client
        self.api = SentinelAPI(
            self.username,
            self.password,
            "https://catalogue.dataspace.copernicus.eu/resto",
        )

        logger.info("Copernicus API client initialized")

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
        Search for Sentinel-2 scenes.

        Args:
            lat: Center latitude
            lon: Center longitude
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            max_cloud_cover: Maximum cloud cover percentage (0-100)
            product_type: Product type (S2MSI2A for Level-2A)

        Returns:
            List of scene metadata dictionaries
        """
        logger.info(f"Searching Sentinel-2 scenes for ({lat}, {lon})")
        logger.info(f"Date range: {start_date} to {end_date}")
        logger.info(f"Max cloud cover: {max_cloud_cover}%")

        # Validate inputs
        parse_coordinates(lat, lon)
        start_dt, end_dt = validate_date_range(start_date, end_date)

        # Create bounding box (500m radius)
        bbox = create_bbox(lat, lon, radius_m=config.AOI_RADIUS)
        footprint = f"POLYGON(({bbox[0]} {bbox[1]}, {bbox[2]} {bbox[1]}, {bbox[2]} {bbox[3]}, {bbox[0]} {bbox[3]}, {bbox[0]} {bbox[1]}))"

        # Search API
        try:
            products = self.api.query(
                area=footprint,
                date=(start_dt, end_dt),
                platformname="Sentinel-2",
                producttype=product_type,
                cloudcoverpercentage=(0, max_cloud_cover),
            )

            logger.info(f"Found {len(products)} Sentinel-2 scenes")

            # Convert to list of dictionaries
            scenes = []
            for uuid, product in products.items():
                scenes.append(
                    {
                        "uuid": uuid,
                        "title": product["title"],
                        "sensing_date": product["beginposition"].strftime("%Y-%m-%d"),
                        "cloud_cover": product["cloudcoverpercentage"],
                        "size_mb": product["size"].split()[0],
                        "product_type": product["producttype"],
                    }
                )

            # Sort by date (most recent first)
            scenes.sort(key=lambda x: x["sensing_date"], reverse=True)

            return scenes

        except Exception as e:
            logger.error(f"Search failed: {e}")
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
        Search for Sentinel-1 SAR scenes.

        Args:
            lat: Center latitude
            lon: Center longitude
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            product_type: Product type (GRD, SLC)
            polarization: Polarization mode (VV VH, HH HV)

        Returns:
            List of scene metadata dictionaries
        """
        logger.info(f"Searching Sentinel-1 scenes for ({lat}, {lon})")
        logger.info(f"Date range: {start_date} to {end_date}")

        # Validate inputs
        parse_coordinates(lat, lon)
        start_dt, end_dt = validate_date_range(start_date, end_date)

        # Create bounding box
        bbox = create_bbox(lat, lon, radius_m=config.AOI_RADIUS)
        footprint = f"POLYGON(({bbox[0]} {bbox[1]}, {bbox[2]} {bbox[1]}, {bbox[2]} {bbox[3]}, {bbox[0]} {bbox[3]}, {bbox[0]} {bbox[1]}))"

        # Search API
        try:
            products = self.api.query(
                area=footprint,
                date=(start_dt, end_dt),
                platformname="Sentinel-1",
                producttype=product_type,
                polarisationmode=polarization,
            )

            logger.info(f"Found {len(products)} Sentinel-1 scenes")

            scenes = []
            for uuid, product in products.items():
                scenes.append(
                    {
                        "uuid": uuid,
                        "title": product["title"],
                        "sensing_date": product["beginposition"].strftime("%Y-%m-%d"),
                        "polarization": product.get("polarisationmode", "N/A"),
                        "size_mb": product["size"].split()[0],
                        "product_type": product["producttype"],
                    }
                )

            scenes.sort(key=lambda x: x["sensing_date"], reverse=True)

            return scenes

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def download_scene(
        self,
        uuid: str,
        output_dir: Path,
        unzip: bool = True,
    ) -> Optional[Path]:
        """
        Download a satellite scene by UUID.

        Args:
            uuid: Scene UUID from search results
            output_dir: Output directory
            unzip: Whether to unzip SAFE archive

        Returns:
            Path to downloaded scene (or None if failed)
        """
        logger.info(f"Downloading scene: {uuid}")

        # Ensure output directory exists
        ensure_directory(output_dir)

        try:
            # Download scene
            self.api.download(uuid, directory_path=str(output_dir))

            # Find downloaded file
            downloaded_file = None
            for file_path in output_dir.glob("*.zip"):
                if uuid in file_path.name or file_path.stem in uuid:
                    downloaded_file = file_path
                    break

            if not downloaded_file:
                logger.error(f"Downloaded file not found for UUID: {uuid}")
                return None

            logger.info(f"Downloaded: {downloaded_file.name}")
            logger.info(f"Size: {format_file_size(downloaded_file.stat().st_size)}")

            # Unzip if requested
            if unzip:
                logger.info("Extracting SAFE archive...")
                import zipfile

                with zipfile.ZipFile(downloaded_file, "r") as zip_ref:
                    zip_ref.extractall(output_dir)

                # Find extracted SAFE directory
                safe_dir = output_dir / downloaded_file.stem
                if safe_dir.exists():
                    logger.info(f"Extracted to: {safe_dir.name}")
                    return safe_dir
                else:
                    logger.warning("SAFE directory not found after extraction")
                    return downloaded_file
            else:
                return downloaded_file

        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

    def download_multiple(
        self,
        scenes: List[Dict],
        output_dir: Path,
        max_scenes: int = 5,
    ) -> List[Path]:
        """
        Download multiple scenes.

        Args:
            scenes: List of scene dictionaries from search
            output_dir: Output directory
            max_scenes: Maximum number of scenes to download

        Returns:
            List of downloaded scene paths
        """
        downloaded = []

        for i, scene in enumerate(scenes[:max_scenes]):
            logger.info(f"Downloading scene {i+1}/{min(len(scenes), max_scenes)}")
            logger.info(f"  Title: {scene['title']}")
            logger.info(f"  Date: {scene['sensing_date']}")

            scene_path = self.download_scene(
                uuid=scene["uuid"],
                output_dir=output_dir,
                unzip=True,
            )

            if scene_path:
                downloaded.append(scene_path)

        logger.info(f"Downloaded {len(downloaded)}/{max_scenes} scenes successfully")

        return downloaded


def main():
    """
    Command-line interface for satellite data download.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Download Sentinel satellite imagery from Copernicus Data Space"
    )

    parser.add_argument("--lat", type=float, required=True, help="Center latitude")
    parser.add_argument("--lon", type=float, required=True, help="Center longitude")
    parser.add_argument(
        "--start-date", type=str, required=True, help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end-date", type=str, required=True, help="End date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--sensor",
        type=str,
        choices=["sentinel-1", "sentinel-2"],
        default="sentinel-2",
        help="Satellite sensor",
    )
    parser.add_argument(
        "--max-cloud", type=int, default=20, help="Max cloud cover for Sentinel-2 (%)"
    )
    parser.add_argument(
        "--max-scenes", type=int, default=5, help="Maximum scenes to download"
    )
    parser.add_argument("--output", type=str, default=None, help="Output directory")

    args = parser.parse_args()

    # Set up output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = config.RAW_DATA_DIR / f"{args.sensor}_{args.start_date}"

    # Initialize downloader
    downloader = CopernicusDownloader()

    # Search for scenes
    if args.sensor == "sentinel-2":
        scenes = downloader.search_sentinel2(
            lat=args.lat,
            lon=args.lon,
            start_date=args.start_date,
            end_date=args.end_date,
            max_cloud_cover=args.max_cloud,
        )
    else:
        scenes = downloader.search_sentinel1(
            lat=args.lat,
            lon=args.lon,
            start_date=args.start_date,
            end_date=args.end_date,
        )

    if not scenes:
        logger.error("No scenes found matching criteria")
        return

    # Display search results
    logger.info(f"\nFound {len(scenes)} scenes:")
    for i, scene in enumerate(scenes[: args.max_scenes]):
        logger.info(f"  {i+1}. {scene['title']}")
        logger.info(f"     Date: {scene['sensing_date']}")
        if "cloud_cover" in scene:
            logger.info(f"     Cloud: {scene['cloud_cover']}%")
        logger.info(f"     Size: {scene['size_mb']} MB")

    # Download scenes
    logger.info(f"\nDownloading to: {output_dir}")
    downloaded = downloader.download_multiple(
        scenes=scenes,
        output_dir=output_dir,
        max_scenes=args.max_scenes,
    )

    logger.info(f"\n✅ Downloaded {len(downloaded)} scenes")


if __name__ == "__main__":
    from src.utils import setup_logger

    setup_logger(level=config.LOG_LEVEL)
    main()
