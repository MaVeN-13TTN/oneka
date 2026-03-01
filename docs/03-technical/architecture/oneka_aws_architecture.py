#!/usr/bin/env python3
"""
oneka_aws_architecture.py
─────────────────────────
AWS Solutions Architecture diagram for Oneka AI.
Role    : AWS Solutions Architect
Date    : March 1, 2026
Project : Oneka AI — Kenya's Autonomous Infrastructure Audit Platform

Generates
---------
  docs/03-technical/architecture/oneka_aws_architecture.png

AWS services reflected
----------------------
  Compute  : ECS Fargate (FastAPI service + 3 Celery worker pools)
  Database : RDS PostgreSQL 15 + PostGIS 3.4 (db.t3.medium, Multi-AZ)
  Cache    : ElastiCache Redis 7 (cache.t3.micro)  — Celery broker + session cache
  Storage  : S3 (4 buckets: tenders-raw, satellite-archive, tiles, certificates)
  ML / OCR : AWS Textract  — COB BIRR PDF table extraction
  Network  : Application Load Balancer (HTTPS termination)
  Security : IAM (TaskExecutionRole — S3, Textract, RDS access)
  Observe  : CloudWatch (logs, metrics, scraper-health alarms)

External services
-----------------
  e-GP Kenya        egpkenya.go.ke        primary tenders + mandatory GPS coords
  PPIP Portal       ppip.go.ke            historical procurement archive (run once)
  COB BIRR PDFs     cob.go.ke             quarterly expenditure reports
  KMHFR API         api.kmhfr.health.go.ke  5,000+ facility GPS registry
  NCA Registry      nca.go.ke             contractor license database
  Copernicus ESA    dataspace.copernicus.eu  Sentinel-1 SAR + Sentinel-2 optical
  Google Maps       tile.googleapis.com   Photorealistic 3D Tiles (key proxied)

Usage
-----
  # Make sure you are in the base conda environment
  conda activate base
  python docs/03-technical/architecture/oneka_aws_architecture.py

Requirements
------------
  pip install diagrams          # Python library
  sudo apt install graphviz     # system binary (dot)
"""

from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import ECS, Fargate
from diagrams.aws.database import Elasticache, RDS
from diagrams.aws.management import Cloudwatch
from diagrams.aws.ml import Textract
from diagrams.aws.network import ALB
from diagrams.aws.security import IAM
from diagrams.aws.storage import S3
from diagrams.onprem.client import Users
from diagrams.onprem.network import Internet

# ── Output path (same directory as this script) ────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
OUTPUT = str(SCRIPT_DIR / "oneka_aws_architecture")

# ── Graphviz layout settings ───────────────────────────────────────────────────
GRAPH_ATTR = {
    "fontsize": "14",
    "fontname": "Helvetica",
    "bgcolor": "white",
    "pad": "1.0",
    "splines": "ortho",
    "nodesep": "0.65",
    "ranksep": "1.0",
    "concentrate": "false",
}

CLUSTER_ATTR = {
    "fontsize": "12",
    "fontname": "Helvetica Bold",
    "margin": "20",
}

# ── Diagram ────────────────────────────────────────────────────────────────────
with Diagram(
    "Oneka AI  —  AWS Solutions Architecture",
    filename=OUTPUT,
    show=False,
    direction="TB",
    graph_attr=GRAPH_ATTR,
):

    # ── EXTERNAL DATA SOURCES ─────────────────────────────────────────────────
    with Cluster("Kenya Government Data Sources  (Public Internet)",
                 graph_attr={**CLUSTER_ATTR, "bgcolor": "#EBF5FB"}):
        egp   = Internet("e-GP Kenya\negpkenya.go.ke\n(primary • tenders + GPS)")
        ppip  = Internet("PPIP Portal\nppip.go.ke\n(historical archive)")
        cob   = Internet("COB BIRR PDFs\ncob.go.ke\n(quarterly expenditure)")
        kmhfr = Internet("KMHFR API\napi.kmhfr.health.go.ke\n(facility GPS registry)")
        nca   = Internet("NCA Registry\nnca.go.ke\n(contractor licenses)")

    with Cluster("Remote Sensing  (ESA Copernicus)",
                 graph_attr={**CLUSTER_ATTR, "bgcolor": "#E8F8F5"}):
        copern = Internet("Copernicus Data Space\ndataspace.copernicus.eu\nSentinel-2 L2A (10 m optical)\nSentinel-1 GRD (10 m SAR)")

    # ── HUMAN ACTORS ─────────────────────────────────────────────────────────
    with Cluster("Auditors  (Primary Users)",
                 graph_attr={**CLUSTER_ATTR, "bgcolor": "#FEF9E7"}):
        oag  = Users("Kenya OAG\nAuditor General's Office")
        eacc = Users("EACC / PPIU\nAnti-corruption analysts")

    # ── AWS INFRASTRUCTURE ────────────────────────────────────────────────────
    with Cluster("AWS  —  af-south-1 (Cape Town)  /  us-east-1 fallback",
                 graph_attr={**CLUSTER_ATTR, "bgcolor": "#FDFEFE"}):

        # ── S3 Object Storage ──────────────────────────────────────────────
        with Cluster("S3 Object Storage  (private, versioned, AES-256)",
                     graph_attr={**CLUSTER_ATTR, "bgcolor": "#FEF5E7"}):
            s3_pdfs  = S3("oneka-tenders-raw\nTender PDFs + contracts")
            s3_sat   = S3("oneka-satellite-archive\nSentinel GeoTIFFs + raw scenes")
            s3_tiles = S3("oneka-tiles\nXYZ tile pyramids\n(NDVI heatmap · SAR change)")
            s3_certs = S3("oneka-certificates\nSection 106B legal PDFs\n(SHA-256 integrity hashes)")

        # ── AWS Managed Services ───────────────────────────────────────────
        with Cluster("AWS Managed Services",
                     graph_attr={**CLUSTER_ATTR, "bgcolor": "#F4ECF7"}):
            textract = Textract("AWS Textract\nCOB BIRR PDF\ntable + form extraction")
            cw       = Cloudwatch("CloudWatch\nLogs · Metrics · Alarms\nScraper health · API latency\nSatellite worker errors")
            iam      = IAM("IAM\nTaskExecutionRole\nS3 · Textract · RDS\ncross-account access")

        # ── Public Subnet ──────────────────────────────────────────────────
        with Cluster("Public Subnet  (HTTPS ingress)",
                     graph_attr={**CLUSTER_ATTR, "bgcolor": "#EAF2FF"}):
            alb = ALB("Application Load Balancer\nHTTPS 443 → /api/v1/*\nHTTP 80  → 301 redirect")

        # ── Private Subnet — Data Layer ────────────────────────────────────
        with Cluster("Private Subnet  —  Data Layer",
                     graph_attr={**CLUSTER_ATTR, "bgcolor": "#E8F5E9"}):
            rds = RDS(
                "Amazon RDS\nPostgreSQL 15 + PostGIS 3.4\ndb.t3.medium · Multi-AZ\n"
                "Tables: projects · procurement_records\n"
                "financial_records · geolocation_records\n"
                "satellite_analyses"
            )
            redis = Elasticache(
                "ElastiCache Redis 7\ncache.t3.micro\n"
                "Celery broker + result backend\n"
                "Google Maps session tokens (3 h TTL)"
            )

        # ── Private Subnet — ECS Fargate Compute ──────────────────────────
        with Cluster("Private Subnet  —  ECS Fargate Compute",
                     graph_attr={**CLUSTER_ATTR, "bgcolor": "#EBF5FB"}):

            api_svc = Fargate(
                "FastAPI Service\n2 vCPU / 4 GB RAM\nuvicorn · /api/v1/*\n"
                "OpenAPI docs · CORS\n"
                "Google Maps API key proxy\n"
                "Rate limiting (slowapi + Redis)"
            )

            with Cluster("Celery Worker Pool  (auto-scaled)",
                         graph_attr={**CLUSTER_ATTR, "bgcolor": "#D6EAF8"}):
                w_scrape = Fargate(
                    "Scraping Workers\n1 vCPU / 2 GB\n"
                    "e-GP · PPIP · COB\nKMHFR · NCA\n"
                    "Playwright + httpx async"
                )
                w_sat = Fargate(
                    "Satellite Workers\n4 vCPU / 16 GB\n"
                    "Satpy NDVI (Sentinel-2)\n"
                    "PyroSAR + SNAP SAR (Sentinel-1)\n"
                    "NDWI flood filter\n"
                    "gdal2tiles → XYZ pyramid"
                )
                w_ml = Fargate(
                    "ML / Scoring Workers\n2 vCPU / 8 GB\n"
                    "spaCy NER + RapidFuzz\n"
                    "FeatureEngineer (10 features)\n"
                    "RandomForest ghost_detector_v1.pkl\n"
                    "DivergenceService (GREEN/YELLOW/RED)\n"
                    "WeasyPrint Section 106B PDF"
                )

    # ── EXTERNAL SAAS APIS ────────────────────────────────────────────────────
    with Cluster("External SaaS APIs",
                 graph_attr={**CLUSTER_ATTR, "bgcolor": "#FDEDEC"}):
        gmaps = Internet(
            "Google Maps\nPhotorealistic 3D Tiles API\ntile.googleapis.com\n"
            "(API key injected server-side —\nnever reaches browser)"
        )

    # ── FRONTEND (SEPARATE DEPLOYMENT) ────────────────────────────────────────
    with Cluster("Frontend  —  Separate Deployment (Vercel / CDN)",
                 graph_attr={**CLUSTER_ATTR, "bgcolor": "#F5EEF8"}):
        frontend = Internet(
            "Next.js 16 Dashboard\nCesiumJS + Google 3D Tiles\n"
            "NDVI / SAR overlay layers\n"
            "Risk heat map (GeoJSON pins)\n"
            "Divergence timeline chart\n"
            "Alert feed (CRITICAL · HIGH)"
        )

    # ═════════════════════════════════════════════════════════════════════════
    # DATA FLOW EDGES
    # ═════════════════════════════════════════════════════════════════════════

    # 1. Government portals → scraping workers (async Playwright / httpx)
    [egp, ppip, cob, kmhfr, nca] >> Edge(
        label="Playwright / httpx (async)",
        color="steelblue", style="bold"
    ) >> w_scrape

    # 2. Copernicus ESA → satellite workers
    copern >> Edge(
        label="sentinelsat scene download",
        color="teal", style="bold"
    ) >> w_sat

    # 3. Scraping workers → RDS (procurement, financial, geolocation records)
    w_scrape >> Edge(
        label="SQLAlchemy ORM\n(procurement · financial · geolocation)",
        color="darkorange"
    ) >> rds

    # 4. Scraping workers → S3 (raw tender PDFs)
    w_scrape >> Edge(
        label="boto3 PDF upload",
        color="darkorange"
    ) >> s3_pdfs

    # 5. S3 PDFs → Textract → scraping workers (OCR loop for COB BIRR tables)
    s3_pdfs >> Edge(
        label="AnalyzeDocument (tables)",
        color="purple"
    ) >> textract >> Edge(
        label="structured JSON → FinancialRecord",
        color="purple"
    ) >> w_scrape

    # 6. Satellite workers → S3 satellite archive (GeoTIFFs)
    w_sat >> Edge(
        label="GeoTIFF store",
        color="forestgreen"
    ) >> s3_sat

    # 7. Satellite workers → RDS (satellite_analyses rows)
    w_sat >> Edge(
        label="NDVI · SAR · NDWI\nsatellite_analyses rows",
        color="forestgreen"
    ) >> rds

    # 8. Satellite workers → S3 tiles (XYZ tile pyramid upload)
    w_sat >> Edge(
        label="XYZ tile pyramid upload",
        color="forestgreen"
    ) >> s3_tiles

    # 9. RDS features → ML workers → risk scores back to RDS
    rds >> Edge(
        label="feature vectors\n(10 features per project)",
        color="darkviolet"
    ) >> w_ml
    w_ml >> Edge(
        label="ghost_probability · risk_level\n(Project table update)",
        color="darkviolet"
    ) >> rds

    # 10. ML workers → S3 certificates (Section 106B legal PDFs)
    w_ml >> Edge(
        label="Section 106B PDF\n(WeasyPrint + chain-of-custody)",
        color="darkviolet"
    ) >> s3_certs

    # 11. Redis ↔ Celery workers (task queue, Celery Beat scheduler)
    redis >> Edge(
        label="Celery Beat\ntask queue",
        style="dashed", color="slategray"
    ) >> w_scrape
    redis >> Edge(
        label="Celery task queue",
        style="dashed", color="slategray"
    ) >> w_sat
    redis >> Edge(
        label="Celery task queue",
        style="dashed", color="slategray"
    ) >> w_ml

    # 12. FastAPI ↔ database and storage
    api_svc >> Edge(
        label="SQLAlchemy",
        color="darkorange"
    ) >> rds
    api_svc >> Edge(
        label="presigned URL (60 min TTL)",
        color="darkorange"
    ) >> s3_tiles
    api_svc >> Edge(
        label="presigned URL",
        color="darkorange"
    ) >> s3_certs

    # 13. FastAPI ↔ Redis (session cache + task enqueue)
    api_svc >> Edge(
        label="session cache\n+ task enqueue",
        style="dashed", color="slategray"
    ) >> redis

    # 14. FastAPI → Google Maps proxy (API key injected server-side)
    api_svc >> Edge(
        label="tile.googleapis.com\n(key injected server-side)",
        color="crimson", style="bold"
    ) >> gmaps

    # 15. ALB → FastAPI
    alb >> Edge(
        label="HTTPS 443",
        color="navy", style="bold"
    ) >> api_svc

    # 16. Users → ALB (API calls via browser/app)
    [oag, eacc] >> Edge(
        label="HTTPS",
        color="navy"
    ) >> alb

    # 17. Users → Frontend (browser)
    [oag, eacc] >> Edge(
        label="browser",
        color="navy"
    ) >> frontend

    # 18. Frontend → ALB (REST API calls)
    frontend >> Edge(
        label="REST API calls\n/api/v1/*",
        color="navy"
    ) >> alb

    # 19. Frontend → S3 tiles (direct tile fetch for CesiumJS)
    frontend >> Edge(
        label="XYZ tile fetch\n(NDVI · SAR overlays)",
        color="teal"
    ) >> s3_tiles

    # 20. Observability (dotted — all compute → CloudWatch)
    [api_svc, w_scrape, w_sat, w_ml] >> Edge(
        style="dotted", color="lightgray",
        label="logs + metrics"
    ) >> cw

    # 21. IAM → compute (dotted — role attachment)
    iam >> Edge(style="dotted", color="lightgray") >> api_svc
    iam >> Edge(style="dotted", color="lightgray") >> w_scrape


print(f"\n✅  Diagram written to: {OUTPUT}.png\n")
