"""
Seed training projects from satellite/data/training/training_projects.csv
into the PostgreSQL database.

Creates:
  - 30 Project rows (one per training project)
  - 30 GeolocationRecord rows (lat/lon from CSV, PostGIS point)

Usage (run from backend/ directory):
  python scripts/seed_training_projects.py
  python scripts/seed_training_projects.py --dry-run
  python scripts/seed_training_projects.py --force   # re-seed even if rows exist
"""

import sys
import csv
import uuid
import argparse
from pathlib import Path
from decimal import Decimal

# Allow running from backend/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import SessionLocal, init_db
from src.models.project import Project, ProjectStatus, ProjectType
from src.models.geolocation import GeolocationRecord


CSV_PATH = Path(__file__).resolve().parent.parent.parent / \
    "satellite" / "data" / "training" / "training_projects.csv"


def infer_project_type(name: str) -> ProjectType:
    """Infer project type from title keywords."""
    name_lower = name.lower()
    if any(k in name_lower for k in ("hospital", "health", "dispensary", "clinic", "medical")):
        return ProjectType.HEALTH
    if any(k in name_lower for k in ("school", "education", "university", "college")):
        return ProjectType.EDUCATION
    if any(k in name_lower for k in ("road", "bridge", "footbridge", "highway", "link road")):
        return ProjectType.ROADS
    if any(k in name_lower for k in ("water", "sewerage", "sewage", "dam", "borehole")):
        return ProjectType.WATER
    if any(k in name_lower for k in ("market", "stall")):
        return ProjectType.MARKETS
    return ProjectType.OTHER


def infer_status(csv_status: str) -> ProjectStatus:
    """Map CSV status (success/ghost) to ProjectStatus enum."""
    if csv_status.strip().lower() == "success":
        return ProjectStatus.COMPLETED
    # Ghost projects are stalled/abandoned in official records
    return ProjectStatus.STALLED


def seed(dry_run: bool = False, force: bool = False) -> None:
    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found at {CSV_PATH}")
        sys.exit(1)

    db = SessionLocal()
    try:
        existing_count = db.query(Project).count()
        if existing_count > 0 and not force:
            print(f"Database already has {existing_count} project(s). "
                  "Use --force to re-seed.")
            return

        if force and existing_count > 0:
            print(f"--force: deleting {existing_count} existing project(s)...")
            if not dry_run:
                db.query(Project).delete()
                db.commit()

        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        print(f"Seeding {len(rows)} training projects from {CSV_PATH}")
        print("" if dry_run else "", end="")

        seeded = 0
        for row in rows:
            project_uuid = uuid.uuid4()
            project_type = infer_project_type(row["project_name"])
            status = infer_status(row["status"])

            project = Project(
                project_uuid=project_uuid,
                project_name=row["project_name"].strip(),
                project_type=project_type,
                county=row["county"].strip(),
                estimated_value_kes=Decimal(row["budget_kes"]),
                status=status,
                risk_level=None,          # Pending ML scoring
                risk_score=None,
                confidence_score=100,     # Ground-truth training data
                geolocation_status="geolocated",
            )

            lat = float(row["latitude"])
            lon = float(row["longitude"])

            geo = GeolocationRecord(
                project_uuid=project_uuid,
                source_system="TRAINING_CSV",
                facility_name=row["project_name"].strip(),
                latitude=Decimal(str(lat)),
                longitude=Decimal(str(lon)),
                match_method="manual",
                match_confidence=100,
                match_score=100,
                verified=True,
                verified_by="seed_training_projects.py",
                address=f"{row['county']} County, Kenya",
            )
            geo.set_geom_from_coordinates()

            label = "GHOST" if row["status"].strip().lower() == "ghost" else "SUCCESS"
            print(f"  [{label}] {row['project_id']:>3}  {row['project_name'][:55]:<55}  "
                  f"{row['county']:<15}  KES {int(row['budget_kes']):>12,}")

            if not dry_run:
                db.add(project)
                db.add(geo)
                db.flush()  # get DB-assigned IDs before next iteration

            seeded += 1

        if not dry_run:
            db.commit()
            print(f"\n✓ Committed {seeded} projects + {seeded} geolocation records")
        else:
            print(f"\n[DRY RUN] Would insert {seeded} projects + {seeded} geolocation records")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Oneka training projects")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be seeded without writing to DB")
    parser.add_argument("--force", action="store_true",
                        help="Delete existing projects and re-seed")
    args = parser.parse_args()

    init_db()
    seed(dry_run=args.dry_run, force=args.force)
