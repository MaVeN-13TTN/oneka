import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.database import SessionLocal
from src.models.geolocation import GeolocationRecord
from src.models.project import Project
from src.models.investigation import Investigation
from src.tasks.satellite_tasks import analyse_project_task

def run_satellite_pipeline():
    project_uuid = "6cdd1a21-c938-48b4-8cea-4a6acba9b465"
    inv_id = "038e4d14-b9e2-4697-8a5d-e27f1a58e3cf"
    lat, lon = -0.5000, 37.2833

    db = SessionLocal()
    try:
        print(f"Setting geolocation for Project UUID: {project_uuid}")
        
        # 1. Update Project Status
        proj = db.query(Project).filter(Project.project_uuid == project_uuid).first()
        if proj:
            proj.geolocation_status = "geolocated"
        else:
            print("Project not found.")
            return

        # 2. Add Geolocation Record
        existing_geo = db.query(GeolocationRecord).filter(GeolocationRecord.project_uuid == project_uuid).first()
        if not existing_geo:
            geo = GeolocationRecord(
                project_uuid=project_uuid,
                source_system="MANUAL_TEST",
                latitude=lat,
                longitude=lon,
                match_method="MANUAL_PIN",
                match_score=100,
                match_confidence=100,
                facility_name="Kerugoya Town",
            )
            geo.set_geom_from_coordinates()
            db.add(geo)

        # 3. Update Investigation status
        inv = db.query(Investigation).filter(Investigation.investigation_id == inv_id).first()
        if inv:
            inv.status = "scoring"  # Move to scoring for satellite
            if not inv.stage_statuses:
                inv.stage_statuses = {}
            inv.stage_statuses["geolocation"] = {
                "status": "done",
                "lat": lat,
                "lon": lon,
                "resolved": True,
            }
            inv.stage_statuses["satellite"] = {"status": "queued"}
            # Ensure JSONB is recognized as mutated
            inv.stage_statuses = dict(inv.stage_statuses)

        db.commit()
        print("Database updated. Geolocation successful.")

        # 4. Trigger Satellite Pipeline
        start_date = "2024-01-01"
        end_date = "2024-06-30"  # keep it small for testing speed
        print(f"Triggering satellite task for {lat}, {lon} ({start_date} to {end_date})...")
        
        analyse_project_task.delay(
            project_uuid=project_uuid,
            lat=lat,
            lon=lon,
            start_date=start_date,
            end_date=end_date,
        )
        print("Task enqueued to Celery. Please check the Celery logs.")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_satellite_pipeline()
