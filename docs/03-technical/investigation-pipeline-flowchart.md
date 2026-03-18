# Oneka AI — Single Project Investigation Flowchart

This diagram outlines the newly added **Single Project Investigation Pipeline**, demonstrating how a targeted investigation flows through the ingestion layer and integrates into the existing end-to-end Oneka AI platform.

## ASCII Flowchart

```text
╔══════════════════════════════════════════════════════════════════════════════════╗
║                    ONEKA AI — SINGLE PROJECT INVESTIGATION FLOW                  ║
║                      Targeted Pipeline & Fallback Logic                          ║
╚══════════════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────── USER TRIGGER (API Layer) ────────────────────────────┐
│                                                                                  │
│       POST /api/v1/investigations/{id}/scrape                                    │
│       (Search terms provided by user)                                            │
│                    │                                                             │
│                    ▼                                                             │
│       POST /api/v1/investigations/{id}/enrich    (Optional)                      │
│       (Perplexity AI query expansion for better scraping context)                │
│                                                                                  │
└────────────────────┬─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌────────────────── ORCHESTRATION ─────────────────────────────────────────────────┐
│                    │                                                             │
│       investigate_project_task.delay(investigation_id)                           │
│                    │  (Celery worker)                                            │
│                    │                                                             │
│       Updates `investigations` table -> stage_statuses JSON                      │
└────────────────────┬─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌───────────── TARGETED SCRAPING LAYER (data/scrapers/) ───────────────────────────┐
│                                                                                  │
│                         ┌──────────────────────┐                                 │
│                         │    EGPScraper        │                                 │
│                         │    (Primary Tier 1)  │                                 │
│                         └──────────┬───────────┘                                 │
│                                    │                                             │
│                         ┌──────────▼───────────┐                                 │
│                         │ EGP Results > 0 ?    │                                 │
│                         └──────────┬───────────┘                                 │
│                                    │                                             │
│               ┌──────YES───────────┴───────────NO───────┐                        │
│               │                                         │                        │
│               │                              ┌──────────▼───────────┐            │
│               │                              │    PPIPScraper       │            │
│               │                              │    (Fallback Source) │            │
│               │                              └──────────┬───────────┘            │
│               │                                         │                        │
│               ▼                                         ▼                        │
│       ProcurementRecord                         ProcurementRecord                │
│       source=EGP                                source=PPIP                      │
│                                                                                  │
│  (Concurrently: NCAScraper, KMHFRScraper, CoBPoller run targeted searches)       │
└────────────────────┬─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌───────── INTEGRATION INTO CORE ONEKA PIPELINE ───────────────────────────────────┐
│                                                                                  │
│  ┌─────────────────────── ConcordanceService ─────────────────────────────-──┐   │
│  │  Links raw records to a canonical Project UUID                            │   │
│  └─────────────────────────────────┬─────────────────────────────────────────┘   │
│                                    │                                             │
│  ┌─────────────────────── GeolocationService ─────────────────────────────-──┐   │
│  │  Tier 1 API, Tier 2 NER, Tier 3 Ward Centroid                             │   │
│  └─────────────────────────────────┬─────────────────────────────────────────┘   │
│                                    │                                             │
│  ┌─────────────────────── Satellite Pipeline ─────────────────────────────-──┐   │
│  │  analyse_project_task (Sentinel-1 SAR, Sentinel-2 NDVI)                   │   │
│  └─────────────────────────────────┬─────────────────────────────────────────┘   │
│                                    │                                             │
│  ┌─────────────────────── Divergence Engine ──────────────────────────────-──┐   │
│  │  compare financial vs physical progress                                   │   │
│  └─────────────────────────────────┬─────────────────────────────────────────┘   │
│                                    │                                             │
│  ┌─────────────────────── ML Engine ──────────────────────────────────────-──┐   │
│  │  score_project_risk_task (ghost_probability)                              │   │
│  └─────────────────────────────────┬─────────────────────────────────────────┘   │
│                                    │                                             │
│  ┌─────────────────────── Certificate Generation ─────────────────────────-──┐   │
│  │  Generate Section 106B Admissible PDF Certificate                         │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Mermaid Flowchart

```mermaid
flowchart TD
    %% ── USER / API ENTRY POINT ───────────────────────────────────────────────
    subgraph API["FASTAPI LAYER"]
        REQ["POST /api/v1/investigations/{id}/scrape\n(User provides search terms)"]
        ENR["POST /api/v1/investigations/{id}/enrich\n(Perplexity AI query expansion - optional)"]
    end

    %% ── INVESTIGATION ORCHESTRATION ──────────────────────────────────────────
    subgraph ORCH["ORCHESTRATION  ·  Celery"]
        MAIN_TASK["investigate_project_task.delay(investigation_id)"]
    end

    %% ── TARGETED SCRAPING WITH FALLBACK ─────────────────────────────────────
    subgraph SCRAPING["TARGETED SCRAPING LAYER"]
        direction TB
        EGP["EGPScraper (Tier 1)\nAttempt targeted search"]
        DECISION{"EGP Results > 0?"}
        PPIP["PPIPScraper (Fallback)\nAttempt targeted search"]
        OTHER["NCAScraper\nKMHFRScraper\nCoBPoller\n(Run targeted searches)"]
    end

    %% ── DATABASE ─────────────────────────────────────────────────────────────
    subgraph DB["PostgreSQL 15"]
        INV_REC["investigations\n(tracks stage_statuses)"]
        P_REC["procurement_records"]
    end

    %% ── EXISTING END-TO-END PIPELINE ────────────────────────────────────────
    subgraph E2E["CORE ONEKA PIPELINE"]
        CONC["ConcordanceService\n(Link raw records to a canonical Project UUID)"]
        GEO["GeolocationService\n(Tier 1 API, Tier 2 NER, Tier 3 Ward)"]
        SAT["analyse_project_task\n(Sentinel 1 SAR & Sentinel 2 NDVI)"]
        DIV["DivergenceService\n(Calculate physical vs financial progress)"]
        ML["score_project_risk_task\n(RandomForest: ghost_probability)"]
        CERT["CertificateService\n(Generate Section 106B Admissible PDF)"]
    end

    %% ── FLOW ────────────────────────────────────────────────────────────────
    REQ --> ENR
    ENR -- "Enriched Context" --> MAIN_TASK
    MAIN_TASK --> INV_REC
    
    MAIN_TASK --> EGP
    MAIN_TASK --> OTHER
    
    EGP --> DECISION
    DECISION -- "Yes" --> P_REC
    DECISION -- "No (Fallback)" --> PPIP
    PPIP --> P_REC
    
    OTHER --> P_REC
    
    P_REC --> CONC
    CONC --> GEO
    GEO -- "Project Geolocated" --> SAT
    SAT --> DIV
    DIV --> ML
    ML --> CERT
    
    %% ── STATUS UPDATES & FEEDBACK ──────────────────────────────────────────
    CONC -. "update stage_statuses" .-> INV_REC
    GEO -. "update stage_statuses" .-> INV_REC
    SAT -. "update stage_statuses" .-> INV_REC
    ML -. "update stage_statuses" .-> INV_REC

    %% ── STYLES ────────────────────────────────────────────────────────────────
    classDef api       fill:#1a1a2e,stroke:#7986cb,color:#fff
    classDef orch      fill:#2d2d2d,stroke:#f5a623,color:#fff
    classDef scraper   fill:#1a3a2a,stroke:#4caf50,color:#fff
    classDef fallback  fill:#4a2a1a,stroke:#d47115,color:#fff
    classDef db        fill:#2d2d2d,stroke:#888,color:#fff
    classDef core      fill:#1e3a5f,stroke:#4a90d9,color:#fff
    
    class REQ,ENR api
    class MAIN_TASK orch
    class EGP,OTHER scraper
    class PPIP fallback
    class INV_REC,P_REC db
    class CONC,GEO,SAT,DIV,ML,CERT core
    class DECISION fallback
```

### Key Differences from Bulk Ingestion:
1. **Targeted Entry Point:** Instead of background cron jobs scraping *everything*, a user explicitly requests an investigation via the API with specific search terms.
2. **Context Enrichment:** An optional `enrich` step (using Perplexity AI) expands simple search terms into highly targeted queries before hitting the government portals.
3. **Sequential Fallback Logic:** The `investigate_project_task` implements smart routing. It tries the primary data source (EGP) first. If EGP returns `0` results (perhaps due to site issues or the tender not being listed), it automatically falls back to the historical/backup registry (PPIP).
4. **State Tracking:** The `investigations` table maintains a `stage_statuses` JSON payload, allowing the frontend to poll and display real-time progress across Scraping, Concordance, Geolocation, Satellite, and ML stages.
