import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.celery_app import celery_app
from src.tasks.ml_tasks import score_project_risk_task
from src.database import SessionLocal
from src.models.project import Project
from src.models.investigation import Investigation

def run_ml_task():
    project_uuid = "6cdd1a21-c938-48b4-8cea-4a6acba9b465"
    inv_id = "038e4d14-b9e2-4697-8a5d-e27f1a58e3cf"

    print(f"Triggering ML task for project: {project_uuid}")
    
    # Trigger task directly to get the result synchronously for testing
    result = score_project_risk_task(project_uuid=project_uuid)
    print("ML Task Result:", result)

    db = SessionLocal()
    proj = db.query(Project).filter(Project.project_uuid == project_uuid).first()
    int_ghost = proj.ghost_probability
    print(f"Project Database Ghost Probability: {int_ghost}")
    
    inv = db.query(Investigation).filter(Investigation.investigation_id == inv_id).first()
    if inv:
        if not inv.stage_statuses:
            inv.stage_statuses = {}
        inv.stage_statuses["ml_scoring"] = {"status": "done", "ghost_probability": result.get("ghost_probability")}
        inv.status = "done"
        inv.stage_statuses = dict(inv.stage_statuses)
        db.commit()
    
    db.close()

if __name__ == "__main__":
    run_ml_task()
