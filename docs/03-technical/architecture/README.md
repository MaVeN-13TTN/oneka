# Oneka AI — AWS Architecture Diagrams

## Contents

| File | Description |
|---|---|
| `oneka_aws_architecture.py` | Python script that generates the architecture diagram |
| `oneka_aws_architecture.png` | Rendered AWS architecture diagram (auto-generated — do not edit manually) |

## Regenerating the Diagram

Requires the base conda environment (diagrams 0.25.1 + graphviz 2.43+):

```bash
conda activate base
python docs/03-technical/architecture/oneka_aws_architecture.py
```

The PNG is written to the same directory as the script.

## What the Diagram Shows

The architecture covers the full Oneka AI backend stack deployed on AWS:

- **External sources** — e-GP Kenya (primary), PPIP archive, COB BIRR PDFs, KMHFR facility registry, NCA, Copernicus ESA
- **ECS Fargate** — FastAPI service + three Celery worker pools (scraping / satellite / ML-scoring)
- **RDS** — PostgreSQL 15 + PostGIS 3.4, Multi-AZ (`projects`, `procurement_records`, `financial_records`, `geolocation_records`, `satellite_analyses`)
- **ElastiCache Redis** — Celery broker, Celery Beat scheduler, Google Maps session token cache
- **S3 (4 buckets)** — `oneka-tenders-raw`, `oneka-satellite-archive`, `oneka-tiles`, `oneka-certificates`
- **AWS Textract** — COB BIRR PDF table extraction
- **ALB** — HTTPS termination, HTTP→HTTPS redirect
- **IAM** — TaskExecutionRole scoped to S3, Textract, RDS
- **CloudWatch** — logs, metrics, scraper-health alarms

Edge colours: blue = scraping flows · orange = DB/S3 writes · green = satellite processing · violet = ML inference · red = secure API proxy · dashed = async Celery queues.

## Dependencies

```
diagrams==0.25.1      # pip install diagrams
graphviz>=2.43        # sudo apt install graphviz  (or brew install graphviz)
```
