"""
Utility functions for satellite data processing.

Common functions used across download, processing, and analysis modules.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from loguru import logger


def setup_logger(log_file: Optional[Path] = None, level: str = "INFO") -> None:
    """
    Configure loguru logger for satellite processing.

    Args:
        log_file: Path to log file (optional)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logger.remove()  # Remove default handler

    # Console handler with colors
    logger.add(
        sink=lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=level,
        colorize=True,
    )

    # File handler (if specified)
    if log_file:
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            level=level,
            rotation="10 MB",
            retention="30 days",
        )


def parse_coordinates(lat: float, lon: float) -> Tuple[float, float]:
    """
    Validate and parse GPS coordinates.

    Args:
        lat: Latitude (-90 to 90)
        lon: Longitude (-180 to 180)

    Returns:
        Tuple of (latitude, longitude)

    Raises:
        ValueError: If coordinates are invalid
    """
    if not -90 <= lat <= 90:
        raise ValueError(f"Invalid latitude: {lat}. Must be between -90 and 90.")

    if not -180 <= lon <= 180:
        raise ValueError(f"Invalid longitude: {lon}. Must be between -180 and 180.")

    return (lat, lon)


def create_bbox(
    lat: float, lon: float, radius_m: float = 500
) -> Tuple[float, float, float, float]:
    """
    Create bounding box around a point.

    Args:
        lat: Center latitude
        lon: Center longitude
        radius_m: Radius in meters (default: 500m)

    Returns:
        Tuple of (min_lon, min_lat, max_lon, max_lat)
    """
    # Approximate degrees per meter at given latitude
    lat_degrees_per_m = 1 / 111320
    lon_degrees_per_m = 1 / (111320 * np.cos(np.radians(lat)))

    lat_offset = radius_m * lat_degrees_per_m
    lon_offset = radius_m * lon_degrees_per_m

    min_lon = lon - lon_offset
    min_lat = lat - lat_offset
    max_lon = lon + lon_offset
    max_lat = lat + lat_offset

    return (min_lon, min_lat, max_lon, max_lat)


def calculate_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """
    Calculate NDVI from NIR and Red bands.

    Formula: (NIR - Red) / (NIR + Red)

    Args:
        nir: Near-infrared band array
        red: Red band array

    Returns:
        NDVI array with values from -1 to 1
    """
    # Avoid division by zero
    denominator = nir + red
    denominator = np.where(denominator == 0, 1e-10, denominator)

    ndvi = (nir - red) / denominator

    # Clip to valid range
    ndvi = np.clip(ndvi, -1.0, 1.0)

    return ndvi


def calculate_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """
    Calculate NDWI (Normalized Difference Water Index).

    Formula: (Green - NIR) / (Green + NIR)

    Args:
        green: Green band array
        nir: Near-infrared band array

    Returns:
        NDWI array with values from -1 to 1
    """
    denominator = green + nir
    denominator = np.where(denominator == 0, 1e-10, denominator)

    ndwi = (green - nir) / denominator
    ndwi = np.clip(ndwi, -1.0, 1.0)

    return ndwi


def extract_statistics(
    array: np.ndarray, mask: Optional[np.ndarray] = None
) -> Dict[str, float]:
    """
    Extract statistical metrics from array.

    Args:
        array: Input array
        mask: Optional boolean mask (True = valid data)

    Returns:
        Dictionary with mean, std, min, max, median, percentiles
    """
    if mask is not None:
        array = array[mask]

    # Remove NaN and infinite values
    array = array[np.isfinite(array)]

    if array.size == 0:
        return {
            "mean": np.nan,
            "std": np.nan,
            "min": np.nan,
            "max": np.nan,
            "median": np.nan,
            "p25": np.nan,
            "p75": np.nan,
        }

    return {
        "mean": float(np.mean(array)),
        "std": float(np.std(array)),
        "min": float(np.min(array)),
        "max": float(np.max(array)),
        "median": float(np.median(array)),
        "p25": float(np.percentile(array, 25)),
        "p75": float(np.percentile(array, 75)),
    }


def format_scene_id(scene_id: str) -> Dict[str, str]:
    """
    Parse Sentinel scene ID into components.

    Example Sentinel-2 ID:
    S2A_MSIL2A_20240615T073611_N0510_R092_T37MCS_20240615T112233

    Args:
        scene_id: Sentinel scene identifier

    Returns:
        Dictionary with parsed components
    """
    parts = scene_id.split("_")

    if scene_id.startswith("S2"):
        return {
            "satellite": parts[0],  # S2A or S2B
            "product_level": parts[1],  # MSIL1C or MSIL2A
            "sensing_date": parts[2],  # YYYYMMDDTHHMMSS
            "processing_baseline": parts[3],  # N0510
            "relative_orbit": parts[4],  # R092
            "tile_id": parts[5],  # T37MCS
            "product_discriminator": parts[6] if len(parts) > 6 else None,
        }
    elif scene_id.startswith("S1"):
        return {
            "satellite": parts[0],  # S1A or S1B
            "mode": parts[1],  # IW (Interferometric Wide Swath)
            "product_type": parts[2],  # GRD
            "sensing_date": parts[4],  # YYYYMMDDTHHMMSS
            "polarization": parts[3],  # VV, VH, etc.
        }
    else:
        return {"raw_id": scene_id}


def create_output_filename(
    sensor: str,
    analysis_type: str,
    date: datetime,
    location: str,
    extension: str = ".tif",
) -> str:
    """
    Create standardized output filename.

    Args:
        sensor: Satellite sensor (e.g., 'Sentinel-2')
        analysis_type: Type of analysis (e.g., 'NDVI', 'SAR_VV')
        date: Acquisition date
        location: Location identifier
        extension: File extension (default: .tif)

    Returns:
        Formatted filename

    Example:
        'Sentinel-2_NDVI_20240615_KIAMBU.tif'
    """
    date_str = date.strftime("%Y%m%d")
    location_clean = location.replace(" ", "_").upper()
    filename = f"{sensor}_{analysis_type}_{date_str}_{location_clean}{extension}"
    return filename


def ensure_directory(path: Path) -> Path:
    """
    Ensure directory exists, create if necessary.

    Args:
        path: Directory path

    Returns:
        Path object
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., '1.5 GB', '234 MB')
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_file_size(file_path: Path) -> str:
    """
    Get file size in human-readable format.

    Args:
        file_path: Path to file

    Returns:
        Formatted file size string
    """
    if not file_path.exists():
        return "0 B"

    size_bytes = file_path.stat().st_size
    return format_file_size(size_bytes)


def validate_date_range(start_date: str, end_date: str) -> Tuple[datetime, datetime]:
    """
    Validate and parse date range.

    Args:
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)

    Returns:
        Tuple of (start_datetime, end_datetime)

    Raises:
        ValueError: If dates are invalid or end < start
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid date format. Use YYYY-MM-DD. Error: {e}")

    if end < start:
        raise ValueError(
            f"End date ({end_date}) must be after start date ({start_date})"
        )

    return (start, end)


def list_safe_directories(directory: Path) -> List[Path]:
    """
    List all Sentinel SAFE directories in a path.

    Args:
        directory: Directory to search

    Returns:
        List of SAFE directory paths
    """
    safe_dirs = []

    if not directory.exists():
        return safe_dirs

    for item in directory.iterdir():
        if item.is_dir() and item.name.endswith(".SAFE"):
            safe_dirs.append(item)

    return sorted(safe_dirs)


def clean_temp_files(directory: Path, pattern: str = "*.tif.aux.xml") -> int:
    """
    Clean temporary processing files.

    Args:
        directory: Directory to clean
        pattern: Glob pattern for files to remove

    Returns:
        Number of files removed
    """
    count = 0

    if not directory.exists():
        return count

    for file_path in directory.glob(pattern):
        try:
            file_path.unlink()
            count += 1
        except Exception as e:
            logger.warning(f"Failed to remove {file_path}: {e}")

    return count
