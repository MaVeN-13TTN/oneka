FROM python:3.12-slim

LABEL maintainer="Oneka AI <dev@oneka.ai>"
LABEL description="ONEKA AI Backend — FastAPI + Celery infrastructure auditing platform"

# System dependencies for:
#   weasyprint (pango, cairo, gdk-pixbuf)
#   geoalchemy2/shapely (geos)
#   psycopg2 (libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango1.0-dev \
    libcairo2-dev \
    libgdk-pixbuf2.0-dev \
    libffi-dev \
    libgeos-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy NLP model (required for Tier 2 geolocation)
RUN python -m spacy download en_core_web_sm

# Copy application source
COPY . .

EXPOSE 8000

# Default: run the API server
# docker-compose.yml overrides this for the worker service
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
