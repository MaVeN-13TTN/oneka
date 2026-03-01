# Sprint Implementation Guide: Backend vs Geospatial Engineer Roles

## Based on Kenya Government Systems Deep Dive Findings

**Date**: February 19, 2026  
**Purpose**: Translate strategic findings into actionable sprint tasks for Backend and Geospatial engineers  
**Context**: Post-e-GP mandatory geolocation discovery (July 2025 ruling)

---

## Executive Summary: How the "Ground Truth" Changes Our Implementation

### The Game Changers

| Finding                     | Impact on Backend Engineer                 | Impact on Geospatial Engineer                         |
| --------------------------- | ------------------------------------------ | ----------------------------------------------------- |
| **e-GP has mandatory GPS**  | Must integrate e-GP as PRIMARY data source | Job shifts from "find location" to "validate quality" |
| **PPIP is historical-only** | One-time import (not continuous scraping)  | No geolocation extraction from PPIP needed            |
| **CoB/e-GP disconnect**     | Build sophisticated matching engine        | Provide GPS validation for matched records            |
| **Triangle of Truth**       | Orchestrate 3-system integration pipeline  | Analyze satellite at GPS provided by e-GP             |

### Role Redefinition

**OLD ASSUMPTION**: Geospatial engineer spends 60% of time finding locations via fuzzy matching  
**NEW REALITY**: Geospatial engineer spends 60% of time validating e-GP GPS quality + satellite analysis

**OLD ASSUMPTION**: Backend engineer scrapes PPIP weekly for new tenders  
**NEW REALITY**: Backend engineer focuses on e-GP integration + CoB-to-e-GP matching

---

## Part 1: Sprint-by-Sprint Breakdown

### Sprint 2 (CURRENT - 90% Complete)

#### Backend Engineer Tasks ✅

```
STATUS: Sprint 2 Nearly Complete (9/10 items done)

✅ COMPLETED:
1. Created Pydantic schemas for procurement (7 schemas)
2. Implemented PPIP web scraper with rate limiting
3. Built S3 storage service for PDFs
4. Created procurement service layer (duplicate detection)
5. Built 8 CRUD API endpoints
6. Fixed database schema (nullable foreign keys)
7. Fixed route ordering (specific before parameterized)
8. Wrote 18 comprehensive tests (all passing)
9. Fixed all type errors (Pyright clean)

⏳ PENDING:
1. Test PPIP scraper with 20+ real tenders (validates before historical import)

📊 METRICS:
- 29/29 tests passing
- 62% code coverage
- 0 type errors
- 4 service modules created
```

#### Geospatial Engineer Tasks (Sprint 2)

```
STATUS: Not applicable - Sprint 2 focused on procurement data pipeline

NOTE: Sprint 2 laid groundwork for Sprint 3 geolocation work:
- Database has geolocation.py models ready
- procurement_records table has nullable project_uuid for linking
- S3 infrastructure ready for satellite imagery storage
```

---

### Sprint 3 (NEXT - Entity Resolution)

#### 🔄 REVISED PRIORITIES (Based on e-GP GPS Discovery)

**ORIGINAL PLAN** (from sprint-planning.md):

```
Focus: Fuzzy matching facilities via KMHFL/NEMIS
Primary approach: String similarity + keyword extraction
Expected success rate: 25-40%
```

**NEW PLAN** (Reality-aligned):

```
Focus: e-GP integration + GPS validation
Primary approach: e-GP OCDS API (or scraping) + quality scoring
Expected success rate: 70-85%
```

---

#### Backend Engineer - Sprint 3 Tasks

##### Task 3.1: e-GP Integration (NEW - CRITICAL)

````python
# Priority: P0 (blocking geospatial work)
# Estimated effort: 5 days
# Dependencies: None

SUBTASKS:
1. Investigate e-GP API access
   - Email National Treasury (support@egpkenya.go.ke)
   - Request OCDS JSON feed access
   - Provide use case: OAG partnership, Article 254 transparency mandate

2. If API approved: Build OCDS client
   File: src/services/egp_ocds_client.py
   ```python
   class EGPOCDSClient:
       """Integration with e-GP Open Contracting Data Standards feed"""

       def fetch_tenders(self, start_date: date, end_date: date) -> List[OCDSTender]:
           """Fetch tenders from OCDS JSON API"""
           pass

       def parse_ocds_release(self, ocds_json: dict) -> TenderRecord:
           """Parse OCDS release to internal TenderRecord format"""
           # Extract: tender.id, tender.title, tender.value.amount
           # Extract: tender.deliveryLocation.geometry.coordinates
           # Extract: awards[0].suppliers, awards[0].contractPeriod
           pass

       def sync_daily_tenders(self) -> int:
           """Daily sync of new/updated tenders"""
           pass
````

3. If API denied: Build e-GP web scraper
   File: src/services/egp_scraper.py

   ```python
   class EGPScraper:
       """Fallback web scraper for egpkenya.go.ke"""

       def scrape_tender_list(self, page: int = 1) -> List[TenderSummary]:
           """Scrape tender list (872 active tenders)"""
           pass

       def scrape_tender_detail(self, tender_id: str) -> TenderDetail:
           """Scrape individual tender page for GPS coordinates"""
           # Look for deliveryLocation in page source or embedded JSON
           pass

       def extract_gps_from_ocds_json(self, page_html: str) -> Optional[GPS]:
           """Extract GPS from OCDS JSON embedded in page"""
           # e-GP website embeds OCDS JSON in script tags
           pass
   ```

4. Database schema update
   File: alembic/versions/[timestamp]\_add_egp_fields.py

   ```python
   # Add e-GP specific fields to procurement_records table
   op.add_column('procurement_records',
       sa.Column('egp_tender_id', sa.Text, nullable=True))
   op.add_column('procurement_records',
       sa.Column('egp_ocds_id', sa.Text, nullable=True))
   op.add_column('procurement_records',
       sa.Column('delivery_latitude', sa.Numeric(10, 7), nullable=True))
   op.add_column('procurement_records',
       sa.Column('delivery_longitude', sa.Numeric(10, 7), nullable=True))
   op.add_column('procurement_records',
       sa.Column('gps_source', sa.Text, nullable=True))  # 'EGP_MANUAL_PIN', 'KMHFL_MATCHED', etc.
   op.add_column('procurement_records',
       sa.Column('gps_quality_score', sa.Integer, nullable=True))  # 0-100
   ```

5. Create e-GP endpoints
   File: src/routers/egp.py

   ```python
   @router.post("/egp/sync")
   async def sync_egp_tenders(days_back: int = 7):
       """Trigger e-GP sync for recent tenders"""
       pass

   @router.get("/egp/stats")
   async def get_egp_stats():
       """Get e-GP integration statistics"""
       return {
           "total_tenders_synced": 4591,
           "tenders_with_gps": 4012,
           "gps_coverage_pct": 87.4,
           "last_sync": "2026-02-19T10:30:00"
       }
   ```

DELIVERABLES:

- ✅ e-GP integration service (API or scraper)
- ✅ Database migration with GPS fields
- ✅ Sync endpoints and tests
- ✅ Documentation: egp-integration-guide.md

HANDOFF TO GEOSPATIAL:

- Provides GPS coordinates for 70-85% of tenders
- Flags GPS quality issues for validation

````

##### Task 3.2: GPS Quality Flagging (SHARED - Backend portion)
```python
# Priority: P0 (enables geospatial validation)
# Estimated effort: 2 days
# Dependencies: Task 3.1 complete

File: src/services/gps_quality_checker.py

class GPSQualityChecker:
    """Preliminary GPS validation (before geospatial deep analysis)"""

    def __init__(self):
        self.county_hq_coords = self._load_county_headquarters()
        self.kenya_boundary = self._load_kenya_boundary()

    def check_gps_quality(self,
                         lat: float,
                         lon: float,
                         county: str,
                         tender_title: str) -> GPSQualityResult:
        """Run basic GPS quality checks"""

        issues = []
        score = 100  # Start with perfect score

        # Check 1: Is it in Kenya?
        if not self._point_in_kenya(lat, lon):
            issues.append("OUTSIDE_KENYA")
            score = 0
            return GPSQualityResult(score=score, issues=issues, status="INVALID")

        # Check 2: Is it in the ocean?
        if self._is_in_ocean(lat, lon):
            issues.append("IN_OCEAN")
            score = 0
            return GPSQualityResult(score=score, issues=issues, status="INVALID")

        # Check 3: County HQ lazy pin?
        county_hq_distance = self._distance_to_county_hq(lat, lon, county)
        if county_hq_distance < 0.5:  # Within 500m of county HQ
            issues.append("COUNTY_HQ_PIN")
            score -= 40
        elif county_hq_distance < 2.0:  # Within 2km
            issues.append("NEAR_COUNTY_HQ")
            score -= 20

        # Check 4: Wrong county?
        if not self._point_in_county(lat, lon, county):
            issues.append("WRONG_COUNTY")
            score -= 30

        # Check 5: Nairobi CBD clustering (for non-Nairobi projects)?
        if county != "Nairobi" and self._is_nairobi_cbd(lat, lon):
            issues.append("NAIROBI_CBD_PIN")
            score -= 35

        # Determine status
        if score >= 80:
            status = "ACCEPTABLE"
        elif score >= 50:
            status = "SUSPECT"
        else:
            status = "INVALID"

        return GPSQualityResult(
            score=max(0, score),
            issues=issues,
            status=status,
            county_hq_distance_km=county_hq_distance,
            recommendation=self._get_recommendation(status)
        )

    def _get_recommendation(self, status: str) -> str:
        recommendations = {
            "ACCEPTABLE": "USE_GPS_AS_IS",
            "SUSPECT": "GEOSPATIAL_VALIDATION_REQUIRED",
            "INVALID": "REJECT_GPS_USE_FALLBACK"
        }
        return recommendations[status]

DELIVERABLES:
- ✅ GPS quality checker service
- ✅ County HQ coordinate database (47 counties)
- ✅ Kenya boundary shapefile integration
- ✅ Quality scoring endpoint

HANDOFF TO GEOSPATIAL:
- Flags "SUSPECT" GPS for deep validation
- Provides "ACCEPTABLE" GPS for immediate use
- Identifies "INVALID" GPS requiring fallback matching
````

##### Task 3.3: KMHFL/NEMIS Fuzzy Matching (DOWNGRADED - Secondary now)

```python
# Priority: P1 (fallback for bad e-GP GPS)
# Estimated effort: 3 days
# Dependencies: Task 3.2 complete
# NOTE: This was originally the PRIMARY approach, now SECONDARY

File: src/services/facility_matcher.py

class FacilityMatcher:
    """Fuzzy match tender titles to facility registries (fallback)"""

    def __init__(self):
        self.kmhfl_facilities = self._load_kmhfl_data()  # Health facilities
        self.nemis_facilities = self._load_nemis_data()  # Schools
        self.kippra_projects = self._load_kippra_data()  # Public projects

    def match_tender_to_facility(self, tender_title: str, county: str) -> List[FacilityMatch]:
        """Find facility matches for tender title"""

        # Extract facility type and name
        facility_type = self._extract_facility_type(tender_title)
        # e.g., "Construction of Ruiru Level 4 Hospital" -> type="hospital"

        # Choose registry
        if facility_type in ["hospital", "dispensary", "health center"]:
            registry = self.kmhfl_facilities
        elif facility_type in ["school", "university", "college"]:
            registry = self.nemis_facilities
        else:
            registry = self.kippra_projects

        # Fuzzy match within county
        candidates = registry[registry['county'] == county]

        matches = []
        for _, facility in candidates.iterrows():
            # String similarity
            title_words = set(tender_title.lower().split())
            facility_words = set(facility['name'].lower().split())

            # Jaccard similarity
            intersection = len(title_words & facility_words)
            union = len(title_words | facility_words)
            similarity = intersection / union if union > 0 else 0

            if similarity > 0.3:  # At least 30% word overlap
                matches.append(FacilityMatch(
                    facility_name=facility['name'],
                    latitude=facility['latitude'],
                    longitude=facility['longitude'],
                    similarity_score=similarity,
                    registry_source=facility['source'],
                    confidence="HIGH" if similarity > 0.6 else "MEDIUM"
                ))

        return sorted(matches, key=lambda x: x.similarity_score, reverse=True)

USAGE FLOW:
1. e-GP provides GPS → Backend runs quality check
2. If GPS score < 50 (INVALID) → Backend runs facility matcher
3. Facility matcher returns top 3 candidates
4. Geospatial engineer validates candidates with satellite imagery
5. Best match stored as fallback GPS

DELIVERABLES:
- ✅ Facility matcher service
- ✅ KMHFL data loader (~15,000 health facilities)
- ✅ NEMIS data loader (~30,000 schools)
- ✅ Matching endpoints with confidence scores
```

##### Task 3.4: Project UUID Resolution & Linking

```python
# Priority: P1 (enables project tracking)
# Estimated effort: 2 days
# Dependencies: Tasks 3.1, 3.2, 3.3 complete

File: src/services/entity_resolution_service.py

class EntityResolutionService:
    """Link procurement records to unified project entities"""

    def resolve_project(self, procurement_record: ProcurementRecord) -> UUID:
        """
        Create or match project entity for procurement record

        Matching logic:
        1. Check if project already exists (by GPS proximity + title similarity)
        2. If exists: Link procurement record to existing project
        3. If new: Create new project entity
        """

        # Look for existing projects within 100m radius
        nearby_projects = self._find_nearby_projects(
            lat=procurement_record.delivery_latitude,
            lon=procurement_record.delivery_longitude,
            radius_km=0.1
        )

        # If found, check title similarity
        for project in nearby_projects:
            title_similarity = self._calculate_title_similarity(
                procurement_record.tender_title,
                project.project_name
            )

            if title_similarity > 0.7:  # 70% title match
                # Same project, different procurement record
                return project.project_uuid

        # No match found, create new project
        new_project = self._create_project_entity(procurement_record)
        return new_project.project_uuid

    def _create_project_entity(self, record: ProcurementRecord) -> Project:
        """Create unified project entity"""

        project = Project(
            project_uuid=uuid4(),
            project_name=record.tender_title,
            project_type=self._infer_project_type(record.tender_title),
            sectors=self._extract_sectors(record.tender_title),
            county=record.county,
            centroid_lat=record.delivery_latitude,
            centroid_lon=record.delivery_longitude,
            geolocation_source="EGP_MANUAL_PIN",
            geolocation_confidence=record.gps_quality_score / 100,
            estimated_cost_kes=record.tender_value_kes,
            construction_start_date=record.contract_start_date,
            expected_completion_date=record.contract_end_date
        )

        db.add(project)
        db.commit()

        # Link procurement record to project
        record.project_uuid = project.project_uuid
        db.commit()

        return project

DELIVERABLES:
- ✅ Entity resolution service
- ✅ Project creation logic
- ✅ Duplicate detection (GPS + title similarity)
- ✅ Sector extraction from tender titles

HANDOFF TO GEOSPATIAL:
- Provides unified project_uuid for satellite tasking
- Each project has single GPS coordinate (centroid)
- Geospatial analysis linked via project_uuid
```

---

#### Geospatial Engineer - Sprint 3 Tasks

##### Task 3.5: GPS Validation Pipeline (NEW - CRITICAL)

```python
# Priority: P0 (validates e-GP GPS quality)
# Estimated effort: 4 days
# Dependencies: Backend Task 3.2 (GPS quality flagging)

File: geospatial/services/gps_validator.py

class GPSValidator:
    """Deep validation of e-GP GPS coordinates using geospatial analysis"""

    def validate_gps(self,
                     lat: float,
                     lon: float,
                     project_type: str,
                     county: str) -> GPSValidationResult:
        """
        Validate GPS coordinates using multiple geospatial checks

        Input: GPS from e-GP (flagged as SUSPECT by backend)
        Output: VERIFIED / ACCEPTABLE / REJECT + evidence
        """

        checks = []

        # Check 1: Land use consistency
        land_use = self._get_land_use_at_location(lat, lon)
        if project_type == "HEALTH_FACILITY" and land_use == "RESIDENTIAL":
            checks.append({
                "check": "land_use",
                "status": "PASS",
                "evidence": "Residential area suitable for health facility"
            })
        elif project_type == "HEALTH_FACILITY" and land_use == "FOREST":
            checks.append({
                "check": "land_use",
                "status": "FAIL",
                "evidence": "Forest area unlikely for health facility"
            })

        # Check 2: Proximity to existing infrastructure
        nearest_road = self._distance_to_nearest_road(lat, lon)
        if nearest_road > 5.0:  # >5km from road
            checks.append({
                "check": "road_access",
                "status": "WARN",
                "evidence": f"No road within 5km (nearest: {nearest_road:.1f}km)"
            })

        # Check 3: Sentinel-2 visual inspection
        # Download recent imagery and check if location makes sense
        recent_image = self._fetch_sentinel2_image(lat, lon, days_back=30)
        visual_check = self._visual_inspection(recent_image, project_type)
        checks.append(visual_check)

        # Check 4: Settlement density (for urban projects)
        if "MARKET" in project_type or "HOSPITAL" in project_type:
            settlement_density = self._calculate_settlement_density(lat, lon, radius_km=2)
            if settlement_density < 100:  # <100 people per km²
                checks.append({
                    "check": "settlement_density",
                    "status": "WARN",
                    "evidence": f"Low population density ({settlement_density}/km²)"
                })

        # Aggregate verdict
        fails = sum(1 for c in checks if c['status'] == 'FAIL')
        warns = sum(1 for c in checks if c['status'] == 'WARN')

        if fails > 0:
            verdict = "REJECT"
            confidence = 30
        elif warns > 1:
            verdict = "SUSPECT"
            confidence = 60
        else:
            verdict = "VERIFIED"
            confidence = 90

        return GPSValidationResult(
            verdict=verdict,
            confidence=confidence,
            checks=checks,
            recommendation=self._get_recommendation(verdict)
        )

DELIVERABLES:
- ✅ GPS validation service with 4+ geospatial checks
- ✅ Land use layer integration (OpenStreetMap or Kenya land use data)
- ✅ Road network proximity analysis
- ✅ Settlement density calculator
- ✅ Visual inspection workflow (Sentinel-2 RGB composite review)

HANDOFF TO BACKEND:
- Updates gps_quality_score in database
- Flags for manual review if REJECT
- Approves for satellite tasking if VERIFIED/ACCEPTABLE
```

##### Task 3.6: Satellite Tasking API (Foundation)

```python
# Priority: P1 (prepares for Sprint 4 analysis)
# Estimated effort: 3 days
# Dependencies: Task 3.5 complete

File: geospatial/services/satellite_tasker.py

class SatelliteTasker:
    """Queue satellite analysis tasks for validated projects"""

    def task_project_analysis(self,
                              project_uuid: UUID,
                              lat: float,
                              lon: float,
                              contract_start_date: date,
                              expected_completion_date: date) -> TaskID:
        """
        Queue satellite analysis for project

        Analysis plan:
        - Baseline image: 30 days before contract_start_date
        - Progress images: Monthly from contract_start to present
        - Final image: Latest available (for ongoing projects)
        """

        task = SatelliteTask(
            task_id=uuid4(),
            project_uuid=project_uuid,
            latitude=lat,
            longitude=lon,
            aoi_buffer_m=500,  # 500m radius around point
            baseline_date=contract_start_date - timedelta(days=30),
            monitoring_start=contract_start_date,
            monitoring_end=expected_completion_date,
            frequency="monthly",
            analysis_type="change_detection",
            priority=self._calculate_priority(contract_value_kes),
            status="QUEUED"
        )

        db.add(task)
        db.commit()

        # Trigger async analysis worker
        celery_app.send_task('geospatial.analyze_project', [task.task_id])

        return task.task_id

    def _calculate_priority(self, contract_value_kes: Decimal) -> int:
        """High-value projects get priority"""
        if contract_value_kes > 100_000_000:  # >KES 100M
            return 1  # High priority
        elif contract_value_kes > 10_000_000:  # >KES 10M
            return 2  # Medium
        else:
            return 3  # Low

DELIVERABLES:
- ✅ Satellite tasking service
- ✅ Priority queue (high-value projects first)
- ✅ Celery background worker setup
- ✅ Task status tracking

HANDOFF TO SPRINT 4:
- Queue ready for Sprint 4 change detection workers
- Foundation for monthly monitoring
```

---

### Sprint 3.5 (NEW - Triangle of Truth Foundation)

This is a NEW mini-sprint based on CoB/e-GP integration discoveries.

#### Backend Engineer - Sprint 3.5 Tasks

##### Task 3.5.1: CoB BIRR PDF Parser

````python
# Priority: P0 (enables Triangle of Truth)
# Estimated effort: 4 days
# Dependencies: None (independent of Sprint 3)

File: src/services/cob_parser.py

class CoB_BIRR_Parser:
    """Parse Controller of Budget Budget Implementation Review Reports"""

    def __init__(self):
        self.pdf_parser = pdfplumber  # or Tabula/Camelot

    def fetch_latest_birr_report(self, level: str = "national") -> Path:
        """
        Download latest BIRR report from cob.go.ke

        Args:
            level: "national" or "county"

        Returns:
            Path to downloaded PDF
        """
        # Scrape cob.go.ke/reports/ for latest quarterly report
        # Download PDF to local/S3 storage
        pass

    def parse_birr_pdf(self, pdf_path: Path) -> List[CoB_Record]:
        """
        Extract tables from BIRR PDF

        Target tables:
        1. Budget Allocation by Ministry/County
        2. Exchequer Releases by Vote Head
        3. Budget Absorption by Entity
        4. Pending Bills
        """

        records = []

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()

                for table in tables:
                    # Identify table type by headers
                    if self._is_budget_allocation_table(table):
                        records.extend(self._parse_allocation_table(table))
                    elif self._is_absorption_table(table):
                        records.extend(self._parse_absorption_table(table))

        return records

    def _parse_allocation_table(self, table: List[List[str]]) -> List[CoB_Record]:
        """
        Parse budget allocation table

        Expected format:
        | Ministry/County | Vote Head | Description | Allocated | Released | Absorbed |
        |-----------------|-----------|-------------|-----------|----------|----------|
        | Min. of Health  | 3001      | Operations  | 500M      | 300M     | 270M     |
        """

        records = []
        headers = table[0]

        for row in table[1:]:  # Skip header
            record = CoB_Record(
                ministry_county=row[0],
                vote_head=row[1],
                vote_head_description=row[2],
                budget_allocated_kes=self._parse_amount(row[3]),
                budget_released_kes=self._parse_amount(row[4]),
                budget_absorbed_kes=self._parse_amount(row[5]),
                reporting_period=self._extract_period_from_pdf(),
                source_document=str(pdf_path)
            )
            records.append(record)

        return records

DELIVERABLES:
- ✅ CoB PDF parser service
- ✅ Table extraction logic (4 table types)
- ✅ Amount parser (handle "KES 500M", "450,000,000", etc.)
- ✅ Quarterly report auto-fetcher
- ✅ Database schema for CoB records

DATABASE SCHEMA:
```sql
CREATE TABLE cob_records (
    cob_record_id UUID PRIMARY KEY,
    ministry_county TEXT NOT NULL,
    vote_head TEXT NOT NULL,
    vote_head_description TEXT,
    budget_allocated_kes DECIMAL(15,2),
    budget_released_kes DECIMAL(15,2),
    budget_absorbed_kes DECIMAL(15,2),
    absorption_rate_pct DECIMAL(5,2),
    reporting_period TEXT,  -- "Q3 2024/25"
    source_document TEXT,
    parsed_at TIMESTAMP DEFAULT NOW()
);
````

````

##### Task 3.5.2: CoB-to-e-GP Matching Engine
```python
# Priority: P0 (core Triangle of Truth logic)
# Estimated effort: 5 days
# Dependencies: Task 3.5.1 + Sprint 3 Task 3.1 (e-GP integration)

File: src/services/triangle_matcher.py

class TriangleMatcher:
    """Match CoB payments to e-GP tenders to Projects"""

    def match_cob_to_egp(self,
                         cob_record: CoB_Record) -> List[MatchCandidate]:
        """
        Find e-GP tenders matching CoB payment record

        Matching signals (weighted):
        1. Entity match (40%): Ministry/County name similarity
        2. Amount match (30%): Budget absorbed ≈ Contract value (±10%)
        3. Keyword match (20%): Vote head description vs tender title
        4. Timing match (10%): Payment period overlaps contract period
        """

        candidates = []

        # Query e-GP database
        egp_tenders = db.query(ProcurementRecord).filter(
            ProcurementRecord.source == 'EGP'
        ).all()

        for tender in egp_tenders:
            score = 0
            signals = {}

            # Signal 1: Entity matching (fuzzy)
            entity_similarity = fuzz.token_set_ratio(
                cob_record.ministry_county.lower(),
                tender.procuring_entity.lower()
            ) / 100
            score += entity_similarity * 40
            signals['entity_match'] = entity_similarity

            # Signal 2: Amount matching
            if tender.tender_value_kes:
                amount_diff_pct = abs(
                    cob_record.budget_absorbed_kes - tender.tender_value_kes
                ) / tender.tender_value_kes

                if amount_diff_pct <= 0.10:  # Within 10%
                    score += 30
                    signals['amount_match'] = 1.0
                elif amount_diff_pct <= 0.20:  # Within 20%
                    score += 15
                    signals['amount_match'] = 0.5
                else:
                    signals['amount_match'] = 0.0

            # Signal 3: Keyword matching
            cob_keywords = set(self._extract_keywords(
                cob_record.vote_head_description
            ))
            tender_keywords = set(self._extract_keywords(
                tender.tender_title
            ))

            keyword_overlap = len(cob_keywords & tender_keywords)
            keyword_score = min(keyword_overlap * 5, 20)  # Max 20 points
            score += keyword_score
            signals['keyword_match'] = keyword_overlap

            # Signal 4: Timing matching
            if self._periods_overlap(
                cob_record.reporting_period,
                tender.contract_start_date,
                tender.contract_end_date
            ):
                score += 10
                signals['timing_match'] = True
            else:
                signals['timing_match'] = False

            # Store candidate
            confidence = "HIGH" if score > 75 else "MEDIUM" if score > 50 else "LOW"

            candidates.append(MatchCandidate(
                cob_record_id=cob_record.cob_record_id,
                egp_tender_id=tender.tender_id,
                project_uuid=tender.project_uuid,
                match_score=score,
                confidence=confidence,
                matching_signals=signals
            ))

        # Return top 5 candidates
        return sorted(candidates, key=lambda x: x.match_score, reverse=True)[:5]

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text"""
        # Remove stopwords, extract nouns
        stopwords = {'the', 'of', 'and', 'for', 'to', 'in', 'a'}
        words = text.lower().split()
        keywords = [w for w in words if w not in stopwords and len(w) > 3]
        return keywords

DELIVERABLES:
- ✅ Multi-factor matching algorithm
- ✅ Confidence scoring (HIGH/MEDIUM/LOW)
- ✅ Top-5 candidate ranking
- ✅ Matching signals breakdown (for audit trail)

DATABASE SCHEMA:
```sql
CREATE TABLE cob_egp_matches (
    match_id UUID PRIMARY KEY,
    cob_record_id UUID REFERENCES cob_records(cob_record_id),
    procurement_record_id UUID REFERENCES procurement_records(procurement_record_id),
    project_uuid UUID REFERENCES projects(project_uuid),
    match_score DECIMAL(5,2),
    confidence VARCHAR(10),  -- HIGH/MEDIUM/LOW
    matching_signals JSONB,
    verified_by_user BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
````

````

##### Task 3.5.3: Triangle of Truth Snapshot Generator
```python
# Priority: P1 (reporting infrastructure)
# Estimated effort: 3 days
# Dependencies: Task 3.5.2 + Geospatial Sprint 4 (satellite analysis)

File: src/services/triangle_generator.py

class TriangleOfTruthGenerator:
    """Generate Triangle of Truth snapshots for projects"""

    def generate_snapshot(self, project_uuid: UUID) -> TriangleSnapshot:
        """
        Create Triangle of Truth snapshot for a project

        Combines:
        1. Financial data (CoB) - % budget absorbed
        2. Procurement data (e-GP) - Contract status
        3. Physical data (Satellite) - % construction complete
        """

        # Fetch data from three systems
        project = db.query(Project).filter_by(project_uuid=project_uuid).first()
        cob_data = self._get_cob_data(project)
        egp_data = self._get_egp_data(project)
        satellite_data = self._get_satellite_data(project)

        # Calculate progress metrics
        financial_progress = self._calculate_financial_progress(cob_data)
        procurement_status = self._get_procurement_status(egp_data)
        physical_progress = self._calculate_physical_progress(satellite_data)

        # Calculate gap
        progress_gap = financial_progress - physical_progress

        # Classify project
        if progress_gap > 60:
            verdict = "CONFIRMED_GHOST_PROJECT"
            risk_score = 95
        elif progress_gap > 30:
            verdict = "SUSPECTED_STALLED_PROJECT"
            risk_score = 70
        elif abs(progress_gap) < 15:
            verdict = "HEALTHY"
            risk_score = 10
        else:
            verdict = "UNDER_REVIEW"
            risk_score = 40

        # Create snapshot
        snapshot = TriangleOfTruthSnapshot(
            snapshot_id=uuid4(),
            project_uuid=project_uuid,
            snapshot_date=date.today(),

            # Financial leg
            cob_source_document=cob_data['source_document'],
            budget_allocated_kes=cob_data['allocated'],
            budget_released_kes=cob_data['released'],
            budget_absorbed_kes=cob_data['absorbed'],
            financial_progress_pct=financial_progress,
            financial_status=cob_data['status'],

            # Procurement leg
            egp_tender_id=egp_data['tender_id'],
            egp_contract_value_kes=egp_data['contract_value'],
            egp_awarded_date=egp_data['award_date'],
            egp_gps_latitude=egp_data['latitude'],
            egp_gps_longitude=egp_data['longitude'],
            egp_gps_validation_status=egp_data['gps_quality'],
            procurement_status=procurement_status,

            # Physical leg
            satellite_analysis_id=satellite_data['analysis_id'],
            physical_progress_pct=physical_progress,
            satellite_interpretation=satellite_data['interpretation'],
            physical_status=satellite_data['status'],

            # Triangle analysis
            progress_gap=progress_gap,
            verdict=verdict,
            risk_score=risk_score
        )

        db.add(snapshot)
        db.commit()

        return snapshot

DELIVERABLES:
- ✅ Triangle snapshot generator
- ✅ Progress gap calculator
- ✅ Verdict classification logic
- ✅ Monthly snapshot automation (Celery task)

API ENDPOINT:
@router.get("/projects/{project_uuid}/triangle-status")
async def get_triangle_status(project_uuid: UUID):
    """Get latest Triangle of Truth status"""
    latest_snapshot = db.query(TriangleOfTruthSnapshot).filter_by(
        project_uuid=project_uuid
    ).order_by(TriangleOfTruthSnapshot.snapshot_date.desc()).first()

    return {
        "financial_leg": {
            "progress": latest_snapshot.financial_progress_pct,
            "status": latest_snapshot.financial_status,
            "released_kes": latest_snapshot.budget_released_kes
        },
        "procurement_leg": {
            "status": latest_snapshot.procurement_status,
            "gps": {
                "lat": latest_snapshot.egp_gps_latitude,
                "lon": latest_snapshot.egp_gps_longitude
            }
        },
        "physical_leg": {
            "progress": latest_snapshot.physical_progress_pct,
            "status": latest_snapshot.physical_status
        },
        "verdict": {
            "classification": latest_snapshot.verdict,
            "risk_score": latest_snapshot.risk_score,
            "progress_gap": latest_snapshot.progress_gap
        }
    }
````

---

### Sprint 4: Satellite Analysis (Backend + Geospatial Collaboration)

#### Geospatial Engineer - Sprint 4 Tasks (PRIMARY FOCUS)

##### Task 4.1: Sentinel-2 Change Detection Pipeline

```python
# Priority: P0 (core satellite analysis)
# Estimated effort: 7 days
# Dependencies: Sprint 3 Task 3.6 (satellite tasking)

File: geospatial/pipelines/change_detection.py

class Sentinel2ChangeDetector:
    """Detect construction activity using Sentinel-2 optical imagery"""

    def analyze_project(self, task: SatelliteTask) -> AnalysisResult:
        """
        Run change detection for project

        Steps:
        1. Fetch baseline image (pre-construction)
        2. Fetch latest image (current state)
        3. Calculate indices (NDVI, NDBI, NDWI)
        4. Detect changes
        5. Estimate construction progress
        """

        # Step 1 & 2: Fetch imagery
        baseline = self._fetch_sentinel2(
            lat=task.latitude,
            lon=task.longitude,
            date=task.baseline_date,
            buffer_m=task.aoi_buffer_m
        )

        current = self._fetch_sentinel2(
            lat=task.latitude,
            lon=task.longitude,
            date=date.today(),
            buffer_m=task.aoi_buffer_m
        )

        # Step 3: Calculate indices
        baseline_ndvi = self._calculate_ndvi(baseline)  # Vegetation
        current_ndvi = self._calculate_ndvi(current)

        baseline_ndbi = self._calculate_ndbi(baseline)  # Built-up
        current_ndbi = self._calculate_ndbi(current)

        # Step 4: Detect changes
        ndvi_change = current_ndvi - baseline_ndvi
        ndbi_change = current_ndbi - baseline_ndbi

        # Construction signatures:
        # - NDVI decreases (vegetation removed)
        # - NDBI increases (built-up area increases)

        construction_pixels = np.where(
            (ndvi_change < -0.2) & (ndbi_change > 0.15)
        )

        construction_area_m2 = len(construction_pixels[0]) * 100  # Sentinel-2 10m pixels

        # Step 5: Estimate progress
        # Assume project AOI is entire buffer (500m radius = ~785,000 m²)
        total_area_m2 = np.pi * (task.aoi_buffer_m ** 2)
        progress_pct = (construction_area_m2 / total_area_m2) * 100

        # Classify status
        if construction_area_m2 < 100:  # <100 m² change
            status = "NON_EXISTENT"
            interpretation = "No construction activity detected"
        elif progress_pct < 20:
            status = "MINIMAL_PROGRESS"
            interpretation = f"{construction_area_m2:.0f} m² cleared, foundation work likely"
        elif progress_pct < 60:
            status = "PARTIAL_CONSTRUCTION"
            interpretation = f"{progress_pct:.0f}% site development, structure emerging"
        else:
            status = "ADVANCED_CONSTRUCTION"
            interpretation = f"{progress_pct:.0f}% complete, building visible"

        return AnalysisResult(
            analysis_id=uuid4(),
            task_id=task.task_id,
            project_uuid=task.project_uuid,
            analysis_date=date.today(),
            baseline_image_date=baseline.acquisition_date,
            current_image_date=current.acquisition_date,
            ndvi_change_mean=float(np.mean(ndvi_change)),
            ndbi_change_mean=float(np.mean(ndbi_change)),
            construction_area_m2=construction_area_m2,
            physical_progress_pct=min(progress_pct, 100),
            status=status,
            interpretation=interpretation,
            confidence=self._calculate_confidence(baseline, current)
        )

DELIVERABLES:
- ✅ Sentinel-2 data fetcher (Google Earth Engine or Copernicus Hub)
- ✅ NDVI calculator (vegetation index)
- ✅ NDBI calculator (built-up index)
- ✅ Change detection algorithm
- ✅ Progress estimation logic
- ✅ Confidence scoring (cloud cover, image quality, etc.)
```

##### Task 4.2: Sentinel-1 SAR Analysis (All-Weather Backup)

```python
# Priority: P1 (backup for cloudy areas)
# Estimated effort: 5 days
# Dependencies: Task 4.1 complete

File: geospatial/pipelines/sar_analysis.py

class Sentinel1SARAnalyzer:
    """Analyze construction using Sentinel-1 SAR (works through clouds)"""

    def analyze_sar(self, task: SatelliteTask) -> SARAnalysisResult:
        """
        SAR change detection

        Advantages:
        - Works through clouds (critical for Kenya's rainy seasons)
        - Detects structural changes (backscatter)

        Disadvantages:
        - Lower resolution (10m vs Sentinel-2's 10m)
        - Requires expertise to interpret
        """

        baseline_sar = self._fetch_sentinel1(
            lat=task.latitude,
            lon=task.longitude,
            date=task.baseline_date,
            polarization='VV'  # Vertical transmit, vertical receive
        )

        current_sar = self._fetch_sentinel1(
            lat=task.latitude,
            lon=task.longitude,
            date=date.today(),
            polarization='VV'
        )

        # Calculate backscatter change
        backscatter_change = current_sar - baseline_sar

        # Construction increases backscatter (smooth soil → rough structure)
        construction_pixels = np.where(backscatter_change > 3)  # >3 dB increase

        construction_area_m2 = len(construction_pixels[0]) * 100

        return SARAnalysisResult(
            backscatter_change_db=float(np.mean(backscatter_change)),
            construction_area_m2=construction_area_m2,
            confidence="MEDIUM"  # SAR harder to interpret
        )

DELIVERABLES:
- ✅ Sentinel-1 SAR data fetcher
- ✅ Backscatter change detection
- ✅ Fallback logic (use SAR if optical has >50% cloud cover)
```

#### Backend Engineer - Sprint 4 Tasks (SUPPORT ROLE)

##### Task 4.3: Satellite Analysis Results API

```python
# Priority: P1 (expose geospatial results to frontend)
# Estimated effort: 2 days
# Dependencies: Geospatial Task 4.1

File: src/routers/satellite.py

@router.get("/satellite/analyses/{project_uuid}")
async def get_project_analyses(project_uuid: UUID):
    """Get all satellite analyses for a project"""

    analyses = db.query(SatelliteAnalysis).filter_by(
        project_uuid=project_uuid
    ).order_by(SatelliteAnalysis.analysis_date.desc()).all()

    return {
        "project_uuid": project_uuid,
        "total_analyses": len(analyses),
        "latest_analysis": analyses[0] if analyses else None,
        "timeline": [
            {
                "date": a.analysis_date,
                "progress_pct": a.physical_progress_pct,
                "status": a.status
            }
            for a in analyses
        ]
    }

@router.post("/satellite/task")
async def task_satellite_analysis(project_uuid: UUID):
    """Manually trigger satellite analysis"""
    # Geospatial engineer's API endpoint
    pass

DELIVERABLES:
- ✅ Satellite analysis CRUD endpoints
- ✅ Timeline API (show progress over time)
- ✅ Manual tasking endpoint (for testing)
```

---

## Part 2: Role Collaboration Matrix

### Who Does What (Sprint-by-Sprint)

| Sprint         | Backend Engineer Focus                                    | Geospatial Engineer Focus                             | Collaboration Points                                       |
| -------------- | --------------------------------------------------------- | ----------------------------------------------------- | ---------------------------------------------------------- |
| **Sprint 2**   | PPIP scraper, S3 storage, CRUD APIs                       | N/A (preparing data pipeline)                         | Database schema design (geolocation fields)                |
| **Sprint 3**   | e-GP integration, GPS quality flagging, facility matching | GPS validation pipeline, satellite tasking foundation | GPS quality handoff (Backend flags → Geo validates)        |
| **Sprint 3.5** | CoB parser, CoB-to-e-GP matching, Triangle generator      | N/A (waiting for satellite analysis)                  | Database schema (Triangle snapshots table)                 |
| **Sprint 4**   | Satellite results API, frontend integration               | Sentinel-2 change detection, SAR analysis             | Analysis result storage (Geo produces → Backend stores)    |
| **Sprint 5**   | Dashboard development, reporting                          | Monthly monitoring automation                         | Progress tracking (Backend queries → Geo provides updates) |

### Data Flow Between Engineers

```
SPRINT 3 FLOW:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Backend:
  1. Fetch tender from e-GP
  2. Extract GPS (lat, lon) from deliveryLocation field
  3. Run basic quality checks (county HQ proximity, boundary check)
  4. Flag GPS as: ACCEPTABLE / SUSPECT / INVALID

  IF SUSPECT:
     └─> Handoff to Geospatial Engineer (via database queue)

Geospatial:
  5. Fetch SUSPECT GPS records from queue
  6. Run deep validation (land use, road access, visual inspection)
  7. Update GPS quality score in database

  IF VERIFIED:
     └─> Mark ready for satellite tasking

  IF REJECT:
     └─> Handoff back to Backend for fallback matching

Backend:
  8. If GPS REJECT, run KMHFL/NEMIS fuzzy matching
  9. Provide top 3 facility candidates

  → Loop back to Geospatial for validation


SPRINT 4 FLOW:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Backend:
  1. Project entity created (has project_uuid + verified GPS)
  2. Trigger satellite tasking via API call to Geospatial service

Geospatial:
  3. Queue satellite analysis task
  4. Fetch Sentinel-2 imagery (baseline + current)
  5. Run change detection pipeline
  6. Calculate physical progress %
  7. Store AnalysisResult in database

Backend:
  8. Query AnalysisResult table
  9. Combine with CoB financial data + e-GP procurement data
  10. Generate Triangle of Truth snapshot
  11. Expose via API to frontend


TRIANGLE OF TRUTH FLOW:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Backend: CoB Parser
  ↓
Backend: CoB-to-e-GP Matcher (finds tender for payment)
  ↓
Backend: Extract GPS from e-GP tender
  ↓
Geospatial: Validate GPS quality
  ↓
Geospatial: Run satellite analysis
  ↓
Backend: Calculate progress gap (financial vs physical)
  ↓
Backend: Generate verdict (Ghost / Stalled / Healthy)
  ↓
Frontend: Display Triangle dashboard
```

---

## Part 3: Skill Requirements by Role

### Backend Engineer Skills Needed

**Sprint 2-3**:

- ✅ Python FastAPI (already using)
- ✅ SQLAlchemy ORM (already using)
- ✅ Web scraping (BeautifulSoup4, requests)
- ✅ PDF parsing (pdfplumber / Tabula / Camelot) ← NEW for CoB
- ✅ Fuzzy string matching (fuzzywuzzy / RapidFuzz) ← NEW for entity matching
- ✅ OCDS/JSON parsing (if e-GP API granted)

**Sprint 3.5-4**:

- Multi-factor matching algorithms (weighted scoring)
- Keyword extraction (NLP basics)
- Celery background tasks (for async processing)
- Data quality scoring logic

**Nice to Have**:

- Machine learning (for improving matching accuracy over time)
- Named Entity Recognition (NER) for better keyword extraction

### Geospatial Engineer Skills Needed

**Sprint 3**:

- ✅ Python geospatial libraries (geopandas, shapely)
- ✅ GIS data handling (shapefiles, GeoJSON)
- ✅ Point-in-polygon checks (county boundaries)
- ✅ Distance calculations (Haversine formula)
- ✅ Land use analysis (OpenStreetMap integration)

**Sprint 4**:

- ✅ Remote sensing fundamentals (spectral indices)
- ✅ Google Earth Engine (or Copernicus Hub API)
- ✅ NDVI/NDBI calculation (vegetation/built-up indices)
- ✅ SAR analysis (Sentinel-1 backscatter)
- ✅ Change detection algorithms
- ✅ Raster processing (numpy, rasterio)

**Sprint 5**:

- Time series analysis (track construction progress over time)
- Cloud masking (handle cloudy pixels)
- Machine learning (classify construction stages)

**Nice to Have**:

- Deep learning (building segmentation with CNNs)
- High-resolution imagery (Planet Labs, Maxar) - if budget allows

---

## Part 4: Success Metrics by Role

### Backend Engineer Metrics

**Sprint 3 Success**:

- [ ] e-GP integration complete (API or scraper)
- [ ] 70%+ of tenders have GPS coordinates
- [ ] GPS quality flagging accuracy >90% (INVALID correctly identified)
- [ ] KMHFL/NEMIS matching >40% success rate (for fallback cases)
- [ ] Entity resolution creates unified project_uuid for >80% of tenders

**Sprint 3.5 Success**:

- [ ] CoB BIRR parser extracts 95%+ of tables correctly
- [ ] CoB-to-e-GP matching: HIGH confidence matches >50% of time
- [ ] Triangle snapshots generated for all matched projects

**Sprint 4 Success**:

- [ ] Satellite analysis results API responds <500ms
- [ ] Triangle status endpoint integrates all 3 data sources
- [ ] Dashboard displays Financial vs Physical progress gap

### Geospatial Engineer Metrics

**Sprint 3 Success**:

- [ ] GPS validation pipeline processes >100 locations/day
- [ ] VERIFIED GPS accuracy >95% (manually checked sample)
- [ ] REJECT GPS →fallback matching success >60%
- [ ] Satellite tasking queue operational (tasks queued without errors)

**Sprint 4 Success**:

- [ ] Change detection runs successfully on >90% of projects
- [ ] Physical progress estimation error <15% (vs manual inspection)
- [ ] Cloud cover <30% on analyzed imagery (otherwise use SAR)
- [ ] SAR analysis provides results when optical unavailable

**Sprint 5 Success**:

- [ ] Monthly monitoring automated (Celery cron job)
- [ ] Time series shows construction progress trend (0% → 100%)
- [ ] Ghost project detection accuracy >85% (vs known cases)

---

## Part 5: Communication Protocol

### Daily Standups (15 min)

**Backend Engineer Updates**:

- "Yesterday: Implemented e-GP OCDS parser, extracted 150 tenders"
- "Today: Running GPS quality checks, will flag SUSPECT for Geo validation"
- "Blockers: Waiting for e-GP API access approval"

**Geospatial Engineer Updates**:

- "Yesterday: Validated 45 GPS coordinates, 38 VERIFIED, 7 REJECT"
- "Today: Starting Sentinel-2 change detection for 10 projects"
- "Blockers: Need project_uuid for 3 tenders (Backend to create)"

### Handoff Points (Async via Database)

**Backend → Geospatial Handoff**:

```sql
-- Backend marks records for geospatial validation
UPDATE procurement_records
SET gps_validation_status = 'PENDING_GEO_REVIEW'
WHERE gps_quality_score < 60;

-- Geospatial engineer queries queue
SELECT * FROM procurement_records
WHERE gps_validation_status = 'PENDING_GEO_REVIEW'
ORDER BY tender_value_kes DESC  -- High-value projects first
LIMIT 50;
```

**Geospatial → Backend Handoff**:

```sql
-- Geospatial completes validation
UPDATE procurement_records
SET gps_quality_score = 85,
    gps_validation_status = 'GEO_VERIFIED',
    validated_by = 'geospatial_engineer',
    validated_at = NOW()
WHERE procurement_record_id = '...';

-- Backend queries verified records
SELECT * FROM procurement_records
WHERE gps_validation_status = 'GEO_VERIFIED'
AND project_uuid IS NULL  -- Not yet linked to project
LIMIT 100;
```

### Weekly Sync (30 min)

**Agenda**:

1. Review metrics (GPS coverage, matching accuracy, satellite analyses)
2. Discuss challenging cases (e.g., GPS in ocean, no facility match found)
3. Plan next week's priorities
4. Adjust workflows based on learnings

**Example Discussion**:

- Backend: "50% of Nairobi projects have GPS at County HQ (lazy pins)"
- Geospatial: "I can validate those with land use analysis, takes 10 min each"
- Decision: "Backend auto-flags Nairobi CBD pins, Geo validates top 20 by value"

---

## Part 6: Risk Management by Role

### Backend Engineer Risks

| Risk                         | Probability | Impact | Mitigation                                         |
| ---------------------------- | ----------- | ------ | -------------------------------------------------- |
| e-GP API access denied       | HIGH        | HIGH   | Build web scraper fallback (2 weeks buffer)        |
| CoB PDF format changes       | MEDIUM      | MEDIUM | Version PDF parser, handle multiple formats        |
| CoB-to-e-GP matching <50%    | MEDIUM      | HIGH   | Implement ML-based matching (Sprint 5 improvement) |
| PPIP historical import fails | LOW         | LOW    | Data is static, can retry indefinitely             |

### Geospatial Engineer Risks

| Risk                             | Probability | Impact | Mitigation                                          |
| -------------------------------- | ----------- | ------ | --------------------------------------------------- |
| Cloud cover >50% (optical fails) | HIGH        | MEDIUM | Use Sentinel-1 SAR as backup                        |
| GPS quality worse than expected  | MEDIUM      | HIGH   | Robust fallback to KMHFL matching (Backend support) |
| Sentinel-2 data quota exceeded   | LOW         | HIGH   | Implement caching, prioritize high-value projects   |
| Change detection false positives | MEDIUM      | MEDIUM | Manual review for risk_score >80 projects           |

---

## Conclusion: The New Reality

### How e-GP Mandatory GPS Changes Everything

**For Backend Engineer**:

- ✅ **EASIER**: Don't need to build complex geolocation from scratch
- ⚠️ **NEW CHALLENGE**: Validate GPS quality (county HQ detection, boundary checks)
- ✅ **NEW OPPORTUNITY**: CoB-to-e-GP matching becomes the "moat" (no one else does this)

**For Geospatial Engineer**:

- ✅ **EASIER**: Start with GPS provided (not searching blind)
- ⚠️ **NEW FOCUS**: Validate GPS via land use, visual inspection, road proximity
- ✅ **MORE TIME**: Spend time on satellite analysis (not location hunting)

### The Triangle of Truth Workflow (Both Engineers)

```
          CoB PAYMENT
         (Backend Parser)
               │
               ↓
        ┌──────────────┐
        │ CoB-to-e-GP  │ ← Backend Multi-Factor Matching
        │   Matcher    │
        └──────┬───────┘
               │
               ↓
          e-GP TENDER
        (with GPS coords)
               │
               ↓
        ┌──────────────┐
        │ GPS Validator│ ← Geospatial Deep Validation
        └──────┬───────┘
               │
               ↓
     SATELLITE ANALYSIS
    (Geospatial Change Detection)
               │
               ↓
        ┌──────────────┐
        │  Triangle    │ ← Backend Aggregation
        │  Generator   │
        └──────┬───────┘
               │
               ↓
    🚨 GHOST PROJECT DETECTED
```

**This is ONEKA's unique value**:

- Backend engineer links **money** (CoB) to **procurement** (e-GP)
- Geospatial engineer links **procurement** (e-GP) to **physical reality** (Satellite)
- Together: First system to connect all three dots

---

**Document Version**: 1.0  
**Date**: February 19, 2026  
**Next Review**: After Sprint 3 kickoff  
**Owner**: ONEKA Technical Team (Backend + Geospatial)
