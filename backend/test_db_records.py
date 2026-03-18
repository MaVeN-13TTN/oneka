import os
import sys

# Ensure imports work
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.database import SessionLocal
from src.models.investigation import Investigation
from src.models.procurement import ProcurementRecord
from sqlalchemy import desc

def fetch_recent_records():
    db = SessionLocal()
    try:
        print("=== RECENT INVESTIGATIONS ===")
        investigations = db.query(Investigation).order_by(desc(Investigation.created_at)).limit(5).all()
        for inv in investigations:
            print(f"- ID: {inv.investigation_id} | Project: '{inv.raw_project_name}' | Status: {inv.status}")
            print(f"  Stage Statuses: {inv.stage_statuses}")
            print(f"  Context: {inv.project_context}")
            print("-" * 50)

        print("\n=== RECENT PROCUREMENT RECORDS ===")
        proc_records = db.query(ProcurementRecord).order_by(desc(ProcurementRecord.created_at)).limit(10).all()
        for rec in proc_records:
            print(f"- ID: {rec.procurement_id} | Tender No: {rec.tender_number} | Source: {rec.source_system}")
            print(f"  Title: {rec.tender_title}")
            print(f"  Inv ID: {rec.investigation_id} | Project UUID: {rec.project_uuid}")
            print("-" * 50)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fetch_recent_records()
