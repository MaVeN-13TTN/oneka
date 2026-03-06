#!/usr/bin/env python3
"""
Load UNOCHA Kenya Level-3 (Ward) boundary GeoJSON into the admin_boundaries table.

Usage:
    python backend/scripts/load_ward_boundaries.py \
        --geojson path/to/ken_admbnda_adm3_iebc_20191031.json

Recommended GeoJSON source (free, open):
    OCHA HDX — Kenya: Admin Level 3 Boundaries
    https://data.humdata.org/dataset/cod-ab-ken

Run from the repo root after applying migration e4f5a1b2c3d0:
    cd /path/to/oneka
    alembic -c backend/alembic.ini upgrade head
    python backend/scripts/load_ward_boundaries.py --geojson <file>
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# ── path wiring ───────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
for _p in [str(_REPO_ROOT), str(_BACKEND_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv

load_dotenv(_BACKEND_ROOT / ".env")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.admin_boundary import AdminBoundary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── property field variants across UNOCHA GeoJSON releases ────────────────────

_WARD_FIELDS = ["ADM3_EN", "shapeName", "WARD_NAME", "NAME_3", "ward_name", "Name"]
_CONST_FIELDS = ["ADM2_EN", "CONST_NAME", "NAME_2", "constituency"]
_COUNTY_FIELDS = ["ADM1_EN", "COUNTY_NAM", "NAME_1", "county"]
_WARD_CODE_FIELDS = ["ADM3_PCODE", "WARD_CODE", "ADM3_CODE", "ward_code"]


def _get(props: dict, candidates: list[str]) -> str | None:
    for key in candidates:
        val = props.get(key)
        if val:
            return str(val).strip()
    return None


def _compute_centroid(geometry: dict) -> tuple[float, float] | None:
    """
    Compute a rough centroid by averaging all ring coordinates.
    Accurate enough for ward-level fallback GPS (Tier 3 quality = 20).
    Uses shapely if available for a proper centroid, otherwise arithmetic mean.
    """
    try:
        from shapely.geometry import shape

        geom = shape(geometry)
        centroid = geom.centroid
        return centroid.y, centroid.x  # lat, lon
    except Exception:
        pass

    # Fallback: average all coordinates
    coords: list[tuple[float, float]] = []
    gtype = geometry.get("type", "")
    raw = geometry.get("coordinates", [])

    try:
        if gtype == "Polygon":
            for ring in raw:
                coords.extend(ring)
        elif gtype == "MultiPolygon":
            for polygon in raw:
                for ring in polygon:
                    coords.extend(ring)
        if not coords:
            return None
        lon_mean = sum(c[0] for c in coords) / len(coords)
        lat_mean = sum(c[1] for c in coords) / len(coords)
        return lat_mean, lon_mean
    except Exception:
        return None


def _build_multipolygon_wkt(geometry: dict) -> str | None:
    """Convert geometry dict to WKT string for geoalchemy2 insertion."""
    try:
        from shapely.geometry import shape
        from shapely import wkt as shapely_wkt

        geom = shape(geometry)
        if geom.geom_type == "Polygon":
            geom = geom.buffer(0)  # ensure valid
            # Wrap in MultiPolygon
            from shapely.geometry import MultiPolygon
            geom = MultiPolygon([geom])
        return f"SRID=4326;{geom.wkt}"
    except Exception:
        return None


def load_boundaries(geojson_path: str, db_url: str | None = None) -> int:
    """
    Parse the GeoJSON file and upsert admin_boundaries rows.
    Returns the number of rows inserted/updated.
    """
    if db_url is None:
        db_url = os.environ.get(
            "DATABASE_URL",
            "postgresql://oneka_user:password@localhost:5432/oneka_dev",
        )

    engine = create_engine(db_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)

    logger.info("Loading ward boundaries from: %s", geojson_path)
    with open(geojson_path, encoding="utf-8") as fh:
        data = json.load(fh)

    features = data.get("features", [])
    logger.info("Features in file: %d", len(features))

    inserted = 0
    skipped = 0

    with Session() as session:
        for feat in features:
            props = feat.get("properties") or {}
            geometry = feat.get("geometry")

            ward_name = _get(props, _WARD_FIELDS)
            if not ward_name:
                skipped += 1
                continue

            ward_code = _get(props, _WARD_CODE_FIELDS)
            constituency = _get(props, _CONST_FIELDS)
            county = _get(props, _COUNTY_FIELDS)

            centroid = _compute_centroid(geometry) if geometry else None
            centroid_lat = centroid[0] if centroid else None
            centroid_lon = centroid[1] if centroid else None

            geom_wkt = _build_multipolygon_wkt(geometry) if geometry else None

            # Upsert by ward_code (unique), or insert if no code
            existing = None
            if ward_code:
                existing = (
                    session.query(AdminBoundary)
                    .filter(AdminBoundary.ward_code == ward_code)
                    .first()
                )

            if existing:
                existing.name = ward_name
                existing.constituency = constituency
                existing.county = county
                existing.centroid_lat = centroid_lat
                existing.centroid_lon = centroid_lon
                if geom_wkt:
                    existing.geom = geom_wkt
            else:
                boundary = AdminBoundary(
                    name=ward_name,
                    ward_code=ward_code,
                    constituency=constituency,
                    county=county,
                    level=3,
                    centroid_lat=centroid_lat,
                    centroid_lon=centroid_lon,
                    geom=geom_wkt,
                )
                session.add(boundary)
                inserted += 1

        session.commit()

    logger.info(
        "Done. Inserted: %d  Updated (existing): %d  Skipped (no name): %d",
        inserted,
        len(features) - inserted - skipped,
        skipped,
    )
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load UNOCHA Kenya L3 ward boundary GeoJSON into admin_boundaries"
    )
    parser.add_argument(
        "--geojson",
        required=True,
        help="Path to Kenya admin level 3 GeoJSON file",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL connection URL (defaults to DATABASE_URL env var)",
    )
    args = parser.parse_args()

    if not Path(args.geojson).exists():
        logger.error("GeoJSON file not found: %s", args.geojson)
        sys.exit(1)

    load_boundaries(args.geojson, args.db_url)


if __name__ == "__main__":
    main()
