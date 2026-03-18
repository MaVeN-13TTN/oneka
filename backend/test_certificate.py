import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.database import SessionLocal
from src.services.certificate_service import CertificateService
from src.models.satellite import SatelliteAnalysis

def test_generate_certificate():
    project_uuid = "6cdd1a21-c938-48b4-8cea-4a6acba9b465"
    db = SessionLocal()
    
    try:
        # 1. Insert dummy satellite record if missing
        existing = db.query(SatelliteAnalysis).filter(SatelliteAnalysis.project_uuid == project_uuid).first()
        if not existing:
            dummy_sat = SatelliteAnalysis(
                project_uuid=project_uuid,
                sensor="Sentinel-2",
                scene_id="S2B_MSIL2A_20240101T075309_N0510_R135_T37NCF_20240101T103738",
                acquisition_date=datetime(2024, 1, 1, 7, 53, 9),
                analysis_type="NDVI_change",
                processing_algorithm="Satpy NDVIProcessor (v1.2)",
                processing_date=datetime.utcnow(),
                cloud_cover_percentage=2.5,
                ndvi_mean=0.35,
                ndvi_slope=-0.01,
                sar_vv_mean=None,
                sar_vh_mean=None,
                sar_backscatter_delta=None,
                interpretation="Normal vegetation detected",
                construction_phase=None,
                image_url="s3://oneka-satellite-scenes/dummy-scene.tif"
            )
            db.add(dummy_sat)
            db.commit()
            print("Inserted dummy SatelliteAnalysis record.")

        # 2. Generate Certificate
        print(f"Generating certificate for project {project_uuid}...")
        service = CertificateService(db)
        pdf_bytes = service.generate_certificate(
            project_uuid=project_uuid,
            analyst_name="Test Analyst",
            analyst_title="Principal Investigator"
        )
        
        # 3. Save to disk
        output_path = "kirinyaga_106b_certificate.pdf"
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
            
        print(f"Success! Certificate saved to {output_path}")

    except Exception as e:
        print(f"Error generating certificate: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_generate_certificate()
