# Oneka AI — Single-Project Investigation Mode

## Architecture Change Design & Implementation Plan

**Date:** March 7, 2026  
**Status:** Proposed  
**Author:** Oneka Engineering

---

## 1. The Problem With Batch Processing

The current Oneka pipeline was designed to scan the entire procurement landscape in bulk — running scrapers against all e-GP Works tenders, downloading every CoB BIRR report, and ingesting the full PPIP/NCA registry. The divergence engine then looks for anomalies across that pool of 10–30 projects.

This works as a surveillance net, but it creates three concrete problems:

**Lack of context.** The scrapers have no idea which project they're looking for. EGPScraper fetches _all_ closed Works tenders. NCAScraper cycles through generic search terms ("Road", "Building", "Hospital") and returns hundreds of unrelated rows. The COB parser matches budget lines using a naive RapidFuzz score against a project name that may not even appear verbatim in the PDF. The result is high noise and brittle matches.

**The PDF problem.** COB BIRR reports are multi-hundred-page government PDFs. `pdfplumber` can extract raw tables, but it has no understanding of which table relates to which project, what the column headers mean on a given page, whether a figure is in thousands or millions, or whether a heading on page 47 still applies to a table on page 53. Without context, the parser guesses. OpenAI Vision over these pages unlocks precise, context-aware extraction — but only if the model knows _what it's looking for_.

**Scraper targeting.** All five scrapers hit their sources without a search target. KMHFL downloads the entire 12,000-facility registry just to fuzzy-match later. This is bandwidth waste for an investigation that only cares about, say, one rural health centre in Bungoma County.

The proposed fix: flip the model. Instead of "scan all, find anomalies", Oneka should let the user nominate **one project** and then intelligently mobilise all five scrapers, the COB parser, and the satellite pipeline around that single investigation.

---

## 2. The New Mental Model

```
               ┌───────────────────────────────────--─┐
               │       USER INVESTIGATION REQUEST     │
               │  Project name + whatever you know    │
               └──────────────────┬────────────────--─┘
                                  │
                                  ▼
               ┌───────────────────────────────────-─┐
               │     PERPLEXITY ENRICHMENT SERVICE   │
               │  Web search → verified project      │
               │  context object (location, dates,   │
               │  budget, contractor, source links)  │
               └──────────────────┬────────────────-─┘
                                  │
               ┌──────────────────▼─────────────────-─┐
               │         PROJECT CONTEXT OBJECT       │
               │  (the "ground truth seed")           │
               └──┬──────┬──────┬──────┬──────┬─────-─┘
                  │      │      │      │      │
                  ▼      ▼      ▼      ▼      ▼
              EGP    PPIP    NCA    CoB    KMHFL
            scraper scraper scraper poller scraper
               (targeted, not bulk)
                  │      │      │      │      │
                  └──────┴──────┴──┬───┘      │
                                   │          │
                                   ▼          ▼
               ┌───────────────────────────────────-─┐
               │   INTELLIGENT PDF PARSER            │
               │   pdfplumber + OpenAI Vision        │
               │   Context-guided table extraction   │
               └──────────────────┬─────────────────-┘
                                   │
                  ┌────────────────▼───────────────-─┐
                  │   EXISTING PIPELINE (unchanged)  │
                  │   Concordance → Geolocation →    │
                  │   Satellite → Divergence → ML →  │
                  │   Certificate                    │
                  └─────────────────────────────────-┘
```

The **Project Context Object** is the new central primitive. Every scraper and every parser receives it. It tells them exactly what to look for, so they can stop fetching thousands of rows and start fetching one.

---

## 3. The Project Context Object

```python
@dataclass
class ProjectContext:
    # --- User-provided seed (minimum required) ---
    project_name: str                    # e.g. "Proposed Bungoma District Hospital"
    user_notes: str | None = None        # free-text user knows

    # --- Perplexity-enriched fields (populated after web search) ---
    canonical_name: str | None = None    # normalised/corrected name
    county: str | None = None
    constituency: str | None = None
    ward: str | None = None
    coordinates: tuple[float, float] | None = None  # (lat, lon) if found online
    project_type: str | None = None      # HEALTH | ROADS | EDUCATION | WATER | OTHER
    estimated_value_kes: float | None = None
    contractor_name: str | None = None
    procuring_entity: str | None = None
    award_date: str | None = None        # ISO 8601
    fiscal_years: list[str] = field(default_factory=list)   # ["2021/2022", "2022/2023"]
    source_urls: list[str] = field(default_factory=list)    # links Perplexity found
    aliases: list[str] = field(default_factory=list)        # alternative name forms

    # --- Scraper targeting hints (derived from above) ---
    search_terms: list[str] = field(default_factory=list)   # for NCA/EGP search
    ministry: str | None = None                              # for COB VOT head lookup
    vote_head: int | None = None                             # explicit if known

    # --- Enrichment metadata ---
    enrichment_confidence: float = 0.0   # 0.0–1.0
    enrichment_source: str = "user"      # "user" | "perplexity" | "hybrid"
    enriched_at: datetime | None = None
```

The key insight: `aliases` and `search_terms` are generated from the enriched context and used directly as the search inputs to all five scrapers. A project named "Proposed Bungoma District Hospital" might appear in e-GP as "CONSTRUCTION OF BUNGOMA DISTRICT HOSPITAL", in the COB BIRR as "District Hospital Bungoma", and in NCA as "Bungoma District Hospital Block A". The aliases list collapses all of those so the scrapers and parser know to accept all forms.

---

## 4. The Perplexity Enrichment Service

### What Perplexity provides

Perplexity is a web search API that returns cited, synthesised answers. For a project like "Bungoma District Hospital", a single Perplexity query can return the procuring entity, the cabinet approval year, the contracting company, the budget line, and links to news articles and county assembly Hansards that mention the project. This is the intelligence layer that transforms a vague user-entered name into a precise set of search targets.

### Service design

```python
# backend/src/services/perplexity_enrichment_service.py

class PerplexityEnrichmentService:

    QUERY_TEMPLATE = """
    You are a Kenya government infrastructure research analyst.
    Find detailed information about the following government-funded
    construction project in Kenya.

    Project name: {project_name}
    User notes: {user_notes}

    Return a JSON object with ONLY the following fields (use null if unknown):
    {{
      "canonical_name": "official project name as it appears in government documents",
      "county": "Kenya county name",
      "constituency": "constituency name",
      "ward": "ward name",
      "coordinates": [latitude, longitude] or null,
      "project_type": one of HEALTH|ROADS|EDUCATION|WATER|MARKETS|OTHER,
      "estimated_value_kes": number in KES or null,
      "contractor_name": "name of contractor/developer",
      "procuring_entity": "full name of government entity procuring",
      "award_date": "YYYY-MM-DD or YYYY or null",
      "fiscal_years": ["YYYY/YYYY", ...],
      "ministry": "Ministry name for COB budget line",
      "vote_head": integer vote head number or null,
      "aliases": ["alternative name 1", "alternative name 2"],
      "source_urls": ["url1", "url2"],
      "confidence": float between 0.0 and 1.0
    }}
    """

    async def enrich(
        self,
        project_name: str,
        user_notes: str | None = None
    ) -> ProjectContext:
        """
        Query Perplexity API with a structured prompt, parse the JSON
        response, derive search_terms, and return a ProjectContext.
        """
        ...

    def _derive_search_terms(self, ctx: ProjectContext) -> list[str]:
        """
        Generate the list of search strings to pass to each scraper.
        Combines canonical_name, aliases, and keyword fragments.

        Example:
          canonical_name = "Construction of Bungoma District Hospital"
          aliases        = ["Bungoma District Hospital", "Bungoma Hospital"]
          county         = "Bungoma"
          project_type   = "HEALTH"

          → search_terms = [
              "Construction of Bungoma District Hospital",
              "Bungoma District Hospital",
              "Bungoma Hospital",
              "Bungoma health",          # county + type keyword
            ]
        """
        ...
```

### API endpoint

```
POST /api/v1/investigations/enrich
Body: { "project_name": "...", "user_notes": "..." }
Response: ProjectContext JSON
```

This endpoint is the first call in the investigation workflow. The frontend (or `curl` for testing) submits the user's input, receives the enriched context, can display it for the user to review/correct, and then proceeds to trigger scraping.

---

## 5. How Each Scraper Changes

### 5.1 EGPScraper — targeted search instead of full fetch

**Current behaviour:** Navigate to TENDERS_URL → click "Closed" → set Category = "Works" → intercept all results.

**New behaviour:** For each `search_term` in `ctx.search_terms`, fill the search box and intercept only matching results. If `ctx.procuring_entity` is known, filter by it as well.

```python
async def fetch(
    self,
    ctx: ProjectContext | None = None   # new optional parameter
) -> list[dict]:
    if ctx is None:
        return await self._fetch_all()   # legacy bulk mode (unchanged)
    return await self._fetch_targeted(ctx)

async def _fetch_targeted(self, ctx: ProjectContext) -> list[dict]:
    # For each search term, fill the search box and collect results.
    # De-duplicate across terms using tender_no.
    ...
```

Because EGP has the search box and JSON API interception, targeted mode works immediately without scraper restructuring — you just drive the search input instead of leaving it blank.

### 5.2 NCAScraper — replace generic SEARCH_TERMS with ctx.search_terms

**Current behaviour:** Loops over 14 hardcoded generic terms ("Road", "Building", …).

**New behaviour:** Uses `ctx.search_terms` directly. One to four targeted terms instead of fourteen, massively reducing noise.

```python
SEARCH_TERMS = ["Road", "Building", ...]  # fallback when no context

async def fetch(
    self,
    ctx: ProjectContext | None = None
) -> list[dict]:
    terms = ctx.search_terms if ctx else self.SEARCH_TERMS
    # rest of method unchanged
```

### 5.3 PPIPScraper — filter API response by known identifiers

PPIP's API returns all active tenders. In targeted mode, filter the response client-side using the project's `aliases` and `procuring_entity`. No scraper architecture change needed — just a post-fetch filter.

```python
async def fetch(
    self,
    ctx: ProjectContext | None = None
) -> list[dict]:
    data = await self._fetch_all()
    if ctx is None:
        return data
    return self._filter_by_context(data, ctx)

def _filter_by_context(
    self,
    data: list[dict],
    ctx: ProjectContext
) -> list[dict]:
    from rapidfuzz import fuzz
    results = []
    for tender in data:
        title = tender.get("title", "") or tender.get("description", "")
        for alias in ctx.aliases + [ctx.canonical_name]:
            if alias and fuzz.token_set_ratio(title, alias) >= 75:
                results.append(tender)
                break
    return results
```

### 5.4 KMHFLScraper — skip bulk download when context has coordinates

If `ctx.coordinates` is already set (Perplexity found the GPS), KMHFL bulk download is unnecessary. If not, the existing cache is used for Tier 2 fuzzy matching as before. No major change needed — just skip the fetch entirely in targeted mode when coordinates are already known.

```python
async def fetch(
    self,
    ctx: ProjectContext | None = None
) -> list[dict]:
    if ctx and ctx.coordinates:
        logger.info("KMHFL: GPS already known from enrichment, skipping bulk fetch.")
        return []   # GeolocationService will use ctx.coordinates directly
    return await self._fetch_all()
```

### 5.5 CoBPoller — targeted scrape by fiscal year

**Current behaviour:** Downloads all available BIRR reports.

**New behaviour:** If `ctx.fiscal_years` is populated, only download reports for those fiscal years. The COB website URL structure encodes year in the filename (`FY-2022-2023`), so targeted downloads are simple glob matching.

```python
async def process(
    self,
    ctx: ProjectContext | None = None
) -> None:
    reports = await self.find_reports()
    if ctx and ctx.fiscal_years:
        reports = [
            r for r in reports
            if any(fy.replace("/", "-") in r["url"] for fy in ctx.fiscal_years)
        ]
    # rest unchanged
```

---

## 6. The Intelligent PDF Parser — pdfplumber + OpenAI Vision

This is the **missing link** the current system lacks.

### Current approach and its limits

`CoBParser.extract_financial_records()` uses `pdfplumber` to extract all tables from a PDF, then searches for tables containing keywords ("Vote", "Approved Budget", "Expenditure") and fuzzy-matches the vote column against the project name. This works when the project name is a close string match to the vote description. It fails when:

- The vote description is an abbreviation or code (e.g., "MOH Vote 401 Sub-vote 06")
- The table spans multiple pages and `pdfplumber` splits it
- The PDF uses image-embedded tables (scanned pages) which `pdfplumber` cannot read at all
- The column structure is non-standard across BIRR quarters
- Key figures appear in narrative text, not in a table

### The new approach

Every PDF page is processed in two stages:

**Stage 1 — pdfplumber structural extraction** (fast, free)

- Extract raw text and table structures
- Identify pages likely to contain relevant content using context keyword matching
- If a page contains at least one context keyword (project name alias, ministry, vote head, procurement entity) — mark it as a "candidate page"
- This narrows a 300-page PDF down to 5–15 candidate pages

**Stage 2 — OpenAI Vision extraction** (precise, context-aware)

- For each candidate page, render it as a high-resolution PNG (200 DPI)
- Send the page image + a structured prompt to `gpt-4o` (vision mode)
- The prompt includes the full `ProjectContext` so the model knows exactly what it is looking for

```python
VISION_PROMPT = """
You are analysing a page from a Kenya Controller of Budget (CoB)
Budget Implementation Review Report (BIRR).

You are looking for budget lines related to this specific project:

  Project name: {canonical_name}
  Also known as: {aliases}
  Procuring entity: {procuring_entity}
  Ministry: {ministry}
  Vote head: {vote_head}
  Fiscal year: {fiscal_year}
  County: {county}

If this page contains data for this project, extract:
  - approved_budget_kes: the Approved Budget figure (in KES)
  - released_kes: the Exchequer Releases figure (in KES)
  - absorbed_kes: the Actual Expenditure figure (in KES)
  - absorption_rate_pct: the absorption rate (as a percentage)
  - reporting_period: the quarter/period this figure covers
  - page_label: the heading or programme label closest to these figures

If the page does NOT contain data for this project, return:
  {{ "match": false }}

Return JSON only. Do not include explanation.
"""
```

### IntelligentCoBParser class design

```python
# data/parsers/intelligent_cob.py

class IntelligentCoBParser:
    """
    Two-stage COB BIRR PDF parser.

    Stage 1: pdfplumber candidate page selection (fast, no API cost)
    Stage 2: OpenAI GPT-4o Vision extraction (targeted, context-aware)
    """

    DPI = 200          # resolution for page rendering
    MAX_PAGES = 300    # safety cap

    def __init__(
        self,
        pdf_path: str,
        ctx: ProjectContext,
        openai_client: AsyncOpenAI,
        max_vision_pages: int = 20,
    ):
        self.pdf_path = pdf_path
        self.ctx = ctx
        self.openai_client = openai_client
        self.max_vision_pages = max_vision_pages

    async def extract(self) -> list[FinancialRecord]:
        """Full two-stage extraction. Returns FinancialRecord-ready dicts."""
        candidate_pages = self._select_candidates()
        results = []
        for page_num in candidate_pages[:self.max_vision_pages]:
            img_bytes = self._render_page(page_num)
            record = await self._vision_extract(page_num, img_bytes)
            if record:
                results.append(record)
        return results

    def _select_candidates(self) -> list[int]:
        """
        Stage 1: Use pdfplumber to find pages containing context keywords.
        Returns 0-based page indices ordered by keyword density (most relevant first).
        """
        keywords = self._build_keyword_set()
        scores: list[tuple[int, int]] = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages[:self.MAX_PAGES]):
                text = (page.extract_text() or "").lower()
                score = sum(1 for kw in keywords if kw.lower() in text)
                if score > 0:
                    scores.append((i, score))
        return [idx for idx, _ in sorted(scores, key=lambda x: -x[1])]

    def _build_keyword_set(self) -> set[str]:
        """Generate keyword set from ProjectContext."""
        kw: set[str] = set()
        if self.ctx.canonical_name:
            kw.add(self.ctx.canonical_name)
        kw.update(self.ctx.aliases)
        if self.ctx.ministry:
            kw.add(self.ctx.ministry)
        if self.ctx.procuring_entity:
            kw.add(self.ctx.procuring_entity)
        if self.ctx.county:
            kw.add(self.ctx.county)
        if self.ctx.vote_head:
            kw.add(str(self.ctx.vote_head))
        return kw

    def _render_page(self, page_num: int) -> bytes:
        """Render a PDF page to PNG bytes using pdf2image (poppler)."""
        from pdf2image import convert_from_path
        images = convert_from_path(
            self.pdf_path,
            dpi=self.DPI,
            first_page=page_num + 1,
            last_page=page_num + 1,
        )
        buf = io.BytesIO()
        images[0].save(buf, format="PNG")
        return buf.getvalue()

    async def _vision_extract(
        self,
        page_num: int,
        img_bytes: bytes,
    ) -> dict | None:
        """
        Stage 2: Send page image to GPT-4o Vision with a targeted prompt.
        Returns a financial record dict or None if no match.
        """
        prompt = self._build_prompt()
        b64 = base64.b64encode(img_bytes).decode()
        response = await self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{b64}",
                        "detail": "high",
                    }},
                ],
            }],
            response_format={"type": "json_object"},
            max_tokens=512,
        )
        raw = json.loads(response.choices[0].message.content)
        if not raw.get("match", True):
            return None
        return self._to_financial_record(raw, page_num)

    def _to_financial_record(self, raw: dict, page_num: int) -> dict:
        """Map Vision output → FinancialRecord-compatible dict."""
        return {
            "source_system": "COB",
            "fiscal_year": self.ctx.fiscal_years[0] if self.ctx.fiscal_years else None,
            "ministry": self.ctx.ministry,
            "vote_head": self.ctx.vote_head,
            "programme": raw.get("page_label"),
            "budget_allocated_kes": raw.get("approved_budget_kes"),
            "budget_released_kes": raw.get("released_kes"),
            "budget_absorbed_kes": raw.get("absorbed_kes"),
            "absorption_rate": raw.get("absorption_rate_pct"),
            "reporting_period": raw.get("reporting_period"),
            "document_source": self.pdf_path,
            "match_method": "openai_vision_gpt4o",
            "confidence_score": 90,  # vision extraction is high confidence
            "extraction_page": page_num,
        }
```

### Why this is the missing link

The current pipeline's quality ceiling is set by `pdfplumber` + `RapidFuzz`. That ceiling is approximately 60% F1 on COB budget matching because government PDF layouts vary wildly quarter to quarter. GPT-4o Vision, given a concrete project context, can read a table in any layout, understand narrative context, and extract figures correctly from scanned pages. Expected improvement: 60% F1 → 90%+ F1 on financial record extraction.

---

## 7. New API Flow — End to End

The full investigation workflow through the existing FastAPI layer:

```
Step 1: Create investigation (POST /api/v1/investigations)
  Body: { "project_name": "...", "user_notes": "..." }
  → Creates an Investigation record in the DB
  → Returns: { investigation_id, status: "created" }

Step 2: Enrich (POST /api/v1/investigations/{id}/enrich)
  → Calls PerplexityEnrichmentService.enrich()
  → Returns: ProjectContext JSON (user can review/edit)

Step 3: Confirm context (PATCH /api/v1/investigations/{id}/context)
  Body: Updated ProjectContext JSON (user corrections)
  → Saves confirmed context to DB

Step 4: Trigger scraping (POST /api/v1/investigations/{id}/scrape)
  → Dispatches Celery task: investigate_project_task(investigation_id)
  → Task calls all five scrapers in parallel, each given the ProjectContext
  → Returns: { celery_task_id }

Step 5: Poll status (GET /api/v1/investigations/{id}/status)
  → Returns stage-by-stage progress:
    {
      "enrichment": "complete",
      "egp_scrape": "complete",
      "ppip_scrape": "complete",
      "nca_scrape": "complete",
      "cob_scrape": "complete",
      "kmhfl_scrape": "complete",
      "pdf_parse": "in_progress",
      "concordance": "pending",
      "geolocation": "pending",
      "satellite": "pending",
      "divergence": "pending",
      "risk_score": "pending",
      "certificate": "pending"
    }

Step 6: Get results (GET /api/v1/investigations/{id}/report)
  → Returns full investigation report:
    {
      project_context,       // enriched context
      procurement_records,   // extracted from scrapers
      financial_records,     // extracted by IntelligentCoBParser
      geolocation,           // resolved GPS
      satellite_analyses,    // if triggered
      divergence_score,
      risk_level,
      ghost_probability,
      certificate_url        // if generated
    }
```

---

## 8. Database Changes

One new table is required. All existing models are unchanged.

```sql
-- Migration: 009_add_investigations.py

CREATE TABLE investigations (
    investigation_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_uuid        UUID REFERENCES projects(project_uuid) ON DELETE SET NULL,

    -- User input
    raw_project_name    TEXT NOT NULL,
    user_notes          TEXT,

    -- Enriched context (stored as JSONB for flexibility)
    project_context     JSONB,
    context_confirmed   BOOLEAN DEFAULT FALSE,
    context_confirmed_at TIMESTAMPTZ,

    -- Pipeline state
    status              VARCHAR(50) DEFAULT 'created',
                        -- created | enriching | enriched | scraping |
                        -- parsing | concordance | geolocating | satellite |
                        -- scoring | complete | failed
    stage_statuses      JSONB DEFAULT '{}',   -- per-stage status map

    -- Audit
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_investigations_created ON investigations(created_at DESC);
CREATE INDEX idx_investigations_project ON investigations(project_uuid);
```

One new column on `procurement_records` and `financial_records` to track which investigation sourced them:

```sql
ALTER TABLE procurement_records  ADD COLUMN investigation_id UUID REFERENCES investigations(investigation_id);
ALTER TABLE financial_records    ADD COLUMN investigation_id UUID REFERENCES investigations(investigation_id);
```

---

## 9. New Environment Variables

```dotenv
# Perplexity web search
PERPLEXITY_API_KEY=pplx-...
PERPLEXITY_MODEL=sonar-pro          # sonar | sonar-pro | sonar-reasoning

# OpenAI Vision (for IntelligentCoBParser)
OPENAI_API_KEY=sk-...
OPENAI_VISION_MODEL=gpt-4o          # gpt-4o | gpt-4o-mini

# Vision parser settings
VISION_MAX_PAGES_PER_PDF=20         # cost control
VISION_CANDIDATE_MIN_SCORE=1        # min keyword hits to qualify as candidate
```

Both keys are added to `backend/src/config.py` (Pydantic Settings) and secrets-managed via the existing `.env` pattern. They are never logged or returned in API responses.

---

## 10. Integration With the Existing Pipeline

All seven downstream stages are unchanged. The investigation system feeds into them, not around them.

```
Investigation Layer (NEW)
│
│   PerplexityEnrichmentService    → produces ProjectContext
│   Targeted scrapers              → produce ProcurementRecord rows
│   IntelligentCoBParser           → produces FinancialRecord rows
│
▼
Stage 2 — Concordance (UNCHANGED)
│   ConcordanceService.link_procurement_to_project()
│   ConcordanceService.link_financial_to_project()
│   → Now trivially accurate because scraper output is already targeted;
│     only one project to link to.
│
▼
Stage 3 — Geolocation (UNCHANGED, enhanced)
│   GeolocationService.resolve() runs the 3-tier strategy as before.
│   Enhancement: Tier 1 can now use ctx.coordinates from Perplexity
│   as a fourth source (quality = 85, method = "perplexity_web_search").
│
▼
Stage 4 — Satellite (UNCHANGED)
│   SatelliteService.queue_analysis() uses resolved GPS from Stage 3.
│
▼
Stage 5 — Divergence (UNCHANGED)
│   DivergenceService.calculate_divergence() uses:
│     - financial_records from IntelligentCoBParser (now higher quality)
│     - satellite_analyses from Stage 4
│
▼
Stage 6 — Risk Assessment (REVISED — see Section 15)
│   MVP phase (0–50 investigations):
│     DivergenceService.calculate_divergence() output is the primary risk signal.
│     divergence_score + alert_level (RED/YELLOW/GREEN) replaces ML output.
│     RiskScoringService is NOT called. ghost_probability = null in reports.
│
│   Growth phase (50+ investigations with verified labels):
│     RiskScoringService.score_project() re-enabled.
│     Model rebuilt as LogisticRegression on real populated feature vectors.
│
▼
Stage 7 — Certificate (UNCHANGED)
    CertificateService.generate_certificate()
```

The key benefit: concordance (Stage 2) which currently struggles with fuzzy matching across dozens of unrelated records now has essentially nothing to do — the records already belong to the right project because the scrapers targeted it from the start.

---

## 11. Implementation Plan

### Sprint 1 — Context Layer (1 week)

**Goal:** `POST /investigations` → `POST /investigations/{id}/enrich` returns a verified ProjectContext.

| Task                                 | File                                                    | Notes                                        |
| ------------------------------------ | ------------------------------------------------------- | -------------------------------------------- |
| Define `ProjectContext` dataclass    | `backend/src/schemas/investigation.py`                  | Pydantic model, JSON-serialisable            |
| Build `PerplexityEnrichmentService`  | `backend/src/services/perplexity_enrichment_service.py` | httpx call, JSON parse, alias derivation     |
| Add `investigations` table migration | `backend/alembic/versions/009_add_investigations.py`    | UUID PK, JSONB context, stage_statuses       |
| Add Investigation ORM model          | `backend/src/models/investigation.py`                   | SQLAlchemy 2.0 style                         |
| Add investigations router            | `backend/src/routers/investigations.py`                 | POST create, POST enrich, PATCH context      |
| Add config keys                      | `backend/src/config.py`                                 | PERPLEXITY_API_KEY, PERPLEXITY_MODEL         |
| Tests                                | `backend/tests/test_investigations.py`                  | Mock Perplexity API, test context derivation |

**Definition of Done:** Given "Proposed Bungoma District Hospital", the enrich endpoint returns a ProjectContext with county, procuring_entity, fiscal_years, and at least two aliases populated.

---

### Sprint 2 — Targeted Scrapers (1 week)

**Goal:** All five scrapers accept an optional `ProjectContext` parameter and use it to narrow their fetch.

| Task                                          | File                                   | Notes                                                          |
| --------------------------------------------- | -------------------------------------- | -------------------------------------------------------------- |
| `EGPScraper.fetch(ctx)` — targeted search     | `data/scrapers/egp.py`                 | Drive search input with ctx.search_terms; de-dupe by tender_no |
| `NCAScraper.fetch(ctx)` — targeted search     | `data/scrapers/nca.py`                 | Replace SEARCH_TERMS with ctx.search_terms                     |
| `PPIPScraper.fetch(ctx)` — post-fetch filter  | `data/scrapers/ppip.py`                | RapidFuzz filter on aliases                                    |
| `CoBPoller.process(ctx)` — fiscal year filter | `data/scrapers/cob.py`                 | Filter by ctx.fiscal_years in URL                              |
| `KMHFLScraper.fetch(ctx)` — skip if GPS known | `data/scrapers/kmhfl.py`               | Return [] when ctx.coordinates set                             |
| Update Celery task                            | `backend/src/tasks/ingestion.py`       | `investigate_project_task(investigation_id)`                   |
| Tests                                         | `data/tests/test_targeted_scrapers.py` | Mock httpx/Playwright, verify targeted output                  |

**Definition of Done:** `investigate_project_task` runs all five scrapers with a mock ProjectContext and inserts only targeted records — zero unrelated procurement rows.

---

### Sprint 3 — Intelligent PDF Parser (1 week)

**Goal:** `IntelligentCoBParser` correctly extracts budget figures for a target project from a real CoB BIRR PDF.

| Task                           | File                                        | Notes                                                         |
| ------------------------------ | ------------------------------------------- | ------------------------------------------------------------- |
| Install `pdf2image` + `openai` | `data/requirements.txt`                     | `pdf2image>=1.17`, `openai>=1.30`                             |
| Build `IntelligentCoBParser`   | `data/parsers/intelligent_cob.py`           | Two-stage: pdfplumber candidates → Vision extraction          |
| Build candidate selection      | `_select_candidates()`                      | Keyword scoring from ProjectContext                           |
| Build page renderer            | `_render_page()`                            | pdf2image at 200 DPI → PNG bytes                              |
| Build Vision extraction        | `_vision_extract()`                         | GPT-4o with structured JSON response                          |
| Wire into `FinancialService`   | `backend/src/services/financial_service.py` | `ingest_cob_report_intelligent(pdf_path, ctx)`                |
| Add config keys                | `backend/src/config.py`                     | OPENAI_API_KEY, OPENAI_VISION_MODEL, VISION_MAX_PAGES_PER_PDF |
| Tests                          | `data/tests/test_intelligent_parser.py`     | Mock OpenAI response, real pdfplumber on test PDF             |

**Definition of Done:** Given a 200-page BIRR PDF and ProjectContext for a health project in Bungoma, the parser returns ≥1 FinancialRecord with budget_allocated_kes, budget_absorbed_kes, and absorption_rate populated, with no unrelated records.

---

### Sprint 4 — Investigation API + Status Polling (1 week)

**Goal:** Full investigation workflow accessible via API: create → enrich → scrape → poll → report.

| Task                                            | File                                                   | Notes                                          |
| ----------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------- |
| `investigate_project_task` Celery task          | `backend/src/tasks/ingestion.py`                       | Parallel scraper calls, stage status updates   |
| Status endpoint                                 | `backend/src/routers/investigations.py`                | GET `/{id}/status` → stage_statuses map        |
| Report endpoint                                 | `backend/src/routers/investigations.py`                | GET `/{id}/report` → full investigation output |
| Wire concordance auto-run                       | `backend/src/services/concordance_service.py`          | Auto-link after scraping completes             |
| Wire geolocation auto-run                       | `backend/src/services/geolocation_service.py`          | Use ctx.coordinates as Tier 0 if available     |
| Wire satellite queue                            | `backend/src/tasks/satellite.py`                       | Auto-trigger after geolocation resolves        |
| Migrate financial_records + procurement_records | `backend/alembic/versions/010_add_investigation_fk.py` | Add investigation_id FK columns                |
| E2E test                                        | `backend/tests/test_e2e_investigation.py`              | Full mocked investigation from POST to report  |

**Definition of Done:** `POST /investigations` → trigger full pipeline → `GET /investigations/{id}/report` returns a complete investigation report with procurement records, financial records, and a risk score.

---

### Sprint 5 — Quality & Hardening (1 week)

| Task                                    | Notes                                                                                |
| --------------------------------------- | ------------------------------------------------------------------------------------ |
| Cost guardrails on Vision calls         | Track OpenAI API spend per investigation, cap at configurable limit                  |
| Perplexity fallback                     | If Perplexity is unavailable, fall back to manual context (user provides all fields) |
| Context edit UI hook                    | PATCH endpoint lets users correct Perplexity results before scraping                 |
| Rate limiting on investigation creation | Max N investigations per hour per API key                                            |
| Coverage gate                           | `backend/tests/` at ≥80% including all new services                                  |
| Update `data/tests/`                    | Tests for all targeted scraper modes                                                 |

---

## 12. What Does Not Change

To be explicit: the following components require **zero modification**:

- `ConcordanceService` — works better with targeted input; no code change
- `GeolocationService` — 3-tier strategy unchanged; gains a new coordinate source
- `DivergenceService` — formula unchanged; becomes the **primary risk signal in the MVP phase**
- `RiskScoringService` — kept in codebase but **not called during MVP**; rebuilt as LogisticRegression in growth phase (see Section 15)
- `CertificateService` — unchanged
- `SatelliteService` — unchanged
- All Alembic migrations 001–008 — unchanged
- All existing tests (281) — unchanged
- Docker Compose / CI configuration — add two new env vars only

The existing batch mode (full-scan scrapers without context) is **preserved** as the default behaviour when no `ProjectContext` is passed. The change is fully additive.

---

## 13. Expected Impact

| Metric                                                      | Before                     | After                                          |
| ----------------------------------------------------------- | -------------------------- | ---------------------------------------------- |
| Procurement record noise (unrelated rows per investigation) | 200–500                    | 0–5                                            |
| Financial record match accuracy (F1)                        | ~60%                       | ~90%                                           |
| Time to full investigation report                           | Full scrape cycle (~hours) | Targeted scrape (~minutes)                     |
| COB parser coverage on scanned PDFs                         | 0% (cannot read)           | ~85%                                           |
| Geolocation confidence for health/education projects        | Tier 2/3 (20–70)           | Tier 0/1 from Perplexity (85–90)               |
| Concordance false links                                     | Moderate                   | Near-zero (single project, already identified) |
| ML feature vector completeness (real populated features)    | 3/10 (7 features are NaN)  | 10/10 after each completed investigation       |
| Ghost detection AUC (RandomForest on synthetic data)        | 0.56 (near-random)         | N/A for MVP; ≥0.80 post-50 real investigations |
| Primary risk signal                                         | RandomForest (unreliable)  | DivergenceService deterministic score (sound)  |

---

## 14. Open Questions

1. **Perplexity model choice.** `sonar-pro` has citation support and is better for factual retrieval. `sonar-reasoning` is better for inferring aliases. Recommend `sonar-pro` with a second pass through `sonar-reasoning` if alias list is empty.

2. **OpenAI Vision cost.** GPT-4o Vision charges per image token. A 200 DPI PNG of a dense table page is ~1,500 image tokens. At 20 pages per PDF and 3 PDFs per investigation: ~90,000 image tokens per investigation. At current GPT-4o pricing this is approximately $0.36 per investigation. Acceptable. `gpt-4o-mini` reduces this to ~$0.04 with lower accuracy.

3. **Context confirmation step.** Perplexity may return incorrect details (e.g., wrong county for a project with an ambiguous name). The PATCH `/context` endpoint lets the user correct the enriched context before scraping begins. Should this be mandatory or optional? Recommend: optional but encouraged via a UI warning if enrichment_confidence < 0.6.

4. **Bulk mode retirement.** The question of whether to deprecate the existing bulk scrape Celery tasks entirely is separate from this implementation. Recommend keeping them for system-wide monitoring and running single-project investigations as a complementary mode.

---

## 15. ML Strategy Revision

### Why the current model scores AUC 0.56

The `ghost_detector_v1.pkl` RandomForest was trained on `satellite/data/training/training_projects.csv` — 30 rows with only four meaningful columns: `project_name`, `county`, `budget_kes`, `status`. The `FeatureEngineer.build_training_dataframe()` method explicitly sets seven of the ten features to `NaN` during training because no satellite or financial computed data exists in the CSV:

```
Features populated from the CSV (3):   contract_value_log, project_type_encoded, county_cloud_risk
Features imputed as column median (7):  ndvi_slope, sar_backscatter_delta, divergence_score,
                                        months_to_clearing, absorption_anomaly,
                                        contractor_tier, phase_on_schedule
```

Because every training row gets the same median-imputed value for seven features, those features carry zero discriminative signal. The model classifies ghost vs. non-ghost using only project type, contract size, and county cloud cover. AUC 0.56 is the correct and expected output — it is barely above random. This is not a bug in the model or the training script; it is a direct consequence of training on metadata-only records when the model was designed to use satellite-derived and financial signals.

The labels in the CSV are genuine (sourced from EACC, OAG, PIC reports). The problem is that the _feature values_ that should correspond to those labels — actual NDVI slopes showing no vegetation clearing, actual absorption rates showing full budget disbursement without physical progress — were never computed and never existed in the training data. The model learned name-to-label correlations, not signal-to-label correlations.

### Why RandomForest cannot be fine-tuned

RandomForest is a batch algorithm. It must be fully retrained from scratch each time new data is added. There is no mechanism to update an existing forest incrementally — the concept of "fine-tuning over time" applies to gradient-descent-based models (neural networks, XGBoost with warm starting). When improving the model over time, the correct approach is: accumulate verified feature vectors in the DB → trigger a full retrain job when the validated dataset crosses a threshold → replace the `.pkl` file atomically. Implementation must be explicit about this to avoid expecting incremental updates.

### The correct role of the 30 synthetic training rows

The 30 rows in `training_projects.csv` serve one legitimate purpose: they are a valid **fixture dataset** for testing that the feature engineering pipeline and `train_model.py` script run to completion without runtime errors. They have no value for producing a reliable ghost probability score. Do not augment them further. Do not run SMOTE on them to expand to 60 or 100. The training dataset size is irrelevant until real feature vectors are available. The entire question of "30 synthetic vs. 10 high-quality" is a false framing — the correct question is "no real feature data vs. real feature data", and real feature data only exists after real investigations complete.

### MVP risk signal: DivergenceService (deterministic)

The `DivergenceService` already computes the correct signal from first principles:

```
divergence_score = financial_progress (absorption_rate %) − physical_progress (from NDVI/SAR)
```

This maps directly onto the definition of a ghost project: money has been disbursed, but no physical construction is detectable. The classification rules are already coded and auditable:

```
RED    divergence > 50   →  CRITICAL — suspected ghost project
YELLOW 20 ≤ d ≤ 50       →  HIGH — stalled or significantly underbuilt
GREEN  < 20              →  LOW/MEDIUM — progressing on track
```

For the MVP, this output **is** the risk assessment. It is deterministic, human-readable, and more defensible under Kenya Evidence Act Section 106B(4) than a probabilistic ML score trained on synthetic metadata. The investigation report presents it directly:

```
Divergence Score:     67 points  →  CRITICAL
Financial absorption: 82%  — Budget substantially disbursed by Treasury
Physical progress:    15%  — Sentinel-2 NDVI shows minimal ground disturbance
Assessment:          SUSPECTED GHOST PROJECT
```

`RiskScoringService.score_project()` is **disabled in the MVP investigation flow**. The `ghost_probability` field in the investigation report is set to `null` with a note: _"Probabilistic ML scoring enabled after 50 validated investigations."_

### Growth phase: rebuild on real data

After sufficient completed investigations with verified labels, the ML pipeline is rebuilt:

| Phase      | Dataset size                 | Model                                       | Rationale                                                                 |
| ---------- | ---------------------------- | ------------------------------------------- | ------------------------------------------------------------------------- |
| Bootstrap  | 0–49 complete investigations | None — DivergenceService only               | Too few samples for any ML model                                          |
| Initial ML | 50–99                        | `LogisticRegression` (L2 regularised)       | Interpretable, produces calibrated probabilities, works correctly at n=50 |
| Upgrade    | 100–199                      | `GradientBoostingClassifier`                | Captures non-linear interactions with sufficient data                     |
| Full ML    | 200+                         | `RandomForestClassifier` or `XGBClassifier` | Ensemble methods justified at this scale                                  |

A new Celery task (`retrain_risk_model_task`) is triggered automatically when the verified-label count passes each threshold. Labels are assigned as follows:

- **Automatic label:** If `divergence_score > 50` AND `absorption_rate > 60` AND `ndvi_slope > -0.01` (no vegetation clearing detected) → label = `ghost`
- **Manual override:** Analyst confirms or corrects label via `PATCH /api/v1/investigations/{id}/label`
- **Audit confirmation:** If a third-party report (OAG, EACC, PIC) is attached via the investigations API, it overrides the automatic label and is stored as the authoritative source

### The 10 real projects: their correct role

Curating 10 high-quality real projects is valuable — but they serve as the **integration test suite and feature engineering benchmark**, not the ML training set.

**Their four purposes:**

1. **Pipeline validation.** Prove that all 10 features are populated (not NaN) after a real investigation completes end-to-end.
2. **Feature sanity check.** Verify that `ndvi_slope` values are in the physically plausible range (−0.10 to +0.05/month), that absorption rates are 0–100%, that divergence scores correlate directionally with known project outcomes.
3. **Parser accuracy baseline.** Confirm that `IntelligentCoBParser` returns the correct budget figures for projects where the ground truth is known from OAG/EACC/Treasury reports.
4. **Regression safety net in CI.** If a code change causes a previously-correct feature to become NaN, these 10 projects catch it before it reaches production.

These 10 projects are curated manually and stored in `satellite/data/training/validation_projects.csv` (separate from `training_projects.csv`). Each must have a verified label, a known budget figure, and a county that has at least partial Sentinel-2 coverage. They are tested in `satellite/tests/test_feature_engineering.py` as integration fixtures, not as training data.
