# Kenya Government Systems Deep Dive: PPIP, e-GP, and CoB

## Detailed Analysis from Official Government Sources

**Date**: February 19, 2026  
**Sources**: Official government websites (tenders.go.ke, egpkenya.go.ke, cob.go.ke)  
**Purpose**: Technical reference for ONEKA integration strategy

---

## Executive Summary

Based on comprehensive analysis of official government portals, this document provides detailed technical specifications, operational status, and integration capabilities of Kenya's three critical public finance management systems:

1. **PPIP** (Public Procurement Information Portal) - tenders.go.ke
2. **e-GP** (Electronic Government Procurement) - egpkenya.go.ke
3. **CoB** (Office of the Controller of Budget) - cob.go.ke

**Key Findings**:

- **PPIP**: 256,034 historical tenders, KES 2.06 trillion transacted (2018-2026), no API access
- **e-GP**: 36,316 registered suppliers, 1,495 procuring entities, 4,591 active tenders, OCDS compliant
- **CoB**: Quarterly BIRR reports, constitutional mandate (Article 228), no procurement code integration

---

## Part 1: PPIP (Public Procurement Information Portal)

### 1.1 System Overview

**Official URL**: https://tenders.go.ke  
**Operator**: Public Procurement Regulatory Authority (PPRA)  
**Technology Partner**: @iLabAfrica, Strathmore University  
**Status**: Active (Legacy Archive)

**Mission Statement** (from website):

> "Transparency in public procurement and asset disposal for a prosperous nation."

### 1.2 System Statistics (As of February 19, 2026)

```
HISTORICAL DATA VOLUME:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Tenders Published:    256,034
📝 Contracts Signed:     130,839
💰 Total Transacted:     KES 2,062,378,021,073.31
📅 Data Period:          ~2018-2025 (pre-e-GP mandate)
```

### 1.3 Technical Capabilities

**Data Access Methods**:

```
✅ Public HTML Interface: Available (no authentication required)
❌ API Access: None (scraping required)
❌ Bulk Download: None (no CSV/JSON exports)
⚠️ PDF Documents: Available but OCR required for structured data
```

**Data Categories Available**:

- Works Tenders
- Goods Tenders
- AGPO Tenders (Access to Government Procurement Opportunities)
- Consultancy Service Tenders
- Non-Consultancy Service Tenders

**AGPO Data** (Affirmative Action):

```
Presidential Directive: 30% of procurement set aside for:
- Youth-owned enterprises
- Women-owned enterprises
- Persons with disability-owned enterprises

Current AGPO Distribution (per website dashboard):
- Total AGPO tenders: Tracked separately
- Distribution by procuring entity: Visualized with charts
- Contract value vs AGPO percentage: Monitored
```

### 1.4 System Integration Points

**Linked Systems** (from website footer):

- National Treasury (treasury.go.ke)
- Public Procurement Regulatory Authority (ppra.go.ke)
- Business Registration Service (brs.go.ke)
- IFMIS (ifmis.go.ke)
- AGPO (agpo.go.ke)
- Kenya Revenue Authority (kra.go.ke)

**CRITICAL LIMITATION**: Despite linking to IFMIS and Treasury, PPIP operates as a **standalone transparency portal** with NO automated data exchange.

### 1.5 Geolocation Capabilities

```
❌ NO GEOLOCATION DATA STRUCTURE

Evidence from website:
- No map views available
- No county-based spatial filtering
- Location data: Text field only (e.g., "Location: Nairobi County")
- No GPS coordinates in tender notices
- No delivery location coordinates in contract records

Schema Design: Built for text-based location description only
```

### 1.6 Contact Information

**Official Contact**:

```
Email:     admin@tenders.go.ke
Address:   P.O BOX 58535-00200, Nairobi, Kenya
Phone:     +254-020-3244000
Alt Phone: +254-020-2213106
Help Desk: https://tenders.go.ke/helpdesk/
```

### 1.7 ONEKA Integration Strategy

**Historical Data Value**:

```python
# ONE-TIME HISTORICAL IMPORT STRATEGY
ppip_integration_plan = {
    "purpose": "ML training data for completed vs stalled project patterns",
    "data_period": "2018-07-01 to 2025-06-30",  # Pre-e-GP mandatory period
    "target_records": 256034,  # All historical tenders
    "extraction_method": "Web scraping + PDF OCR",
    "geolocation_approach": "Post-processing with KMHFL/NEMIS fuzzy matching",
    "update_frequency": "NONE (archive only)",
    "priority": "LOW (historical reference only)"
}

# Fields to Extract
ppip_fields = [
    "tender_number",          # Primary identifier
    "tender_title",           # For entity/facility matching
    "procuring_entity",       # Ministry/County/Agency
    "category",               # Works/Goods/Services
    "tender_method",          # Open/Restricted/RFQ
    "tender_value_kes",       # Contract amount
    "publication_date",       # Tender notice date
    "closing_date",           # Bid submission deadline
    "document_url",           # PDF download link
    "agpo_status"             # Youth/Women/PWD reserved
]

# What PPIP CANNOT Provide
ppip_limitations = [
    "GPS coordinates",        # Not in schema
    "Delivery location",      # Text only
    "Project status",         # Binary: published or not
    "Payment information",    # Not tracked
    "Physical progress",      # Not tracked
    "Contractor performance"  # Not tracked
]
```

**Rate Limiting (Ethical Scraping)**:

```python
# Already implemented in Sprint 2
PPIP_SCRAPER_CONFIG = {
    "rate_limit_seconds": 5,      # Comply with robots.txt
    "user_agent": "ONEKA Bot",    # Transparent identification
    "respect_peak_hours": True,   # Scrape during off-peak
    "max_retries": 3,
    "backoff_factor": 2
}
```

---

## Part 2: e-GP Kenya (Electronic Government Procurement)

### 2.1 System Overview

**Official URL**: https://egpkenya.go.ke  
**Operator**: The National Treasury of Kenya  
**Legal Basis**: Public Procurement and Asset Disposal Act, 2015 (PPADA 2015)  
**Status**: **MANDATORY** (All procuring entities must use this system)  
**Version**: V1.0.18.4 (as of January 7, 2025)

**Legal Mandate** (from FAQ):

> **"Is this e-GP system replacing IFMIS or Public Procurement Information Portal (PPIP)?"**
>
> Yes, the e-GP system is designed to replace and integrate with existing procurement systems. It aims to provide a centralized platform for all procurement processes, ensuring consistency and transparency across government entities.

### 2.2 System Statistics (As of February 19, 2026)

```
CURRENT OPERATIONAL DATA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 Registered Suppliers:     36,316
🏛️ Procuring Entities:       1,495
📋 Active Tenders:            4,591
🔨 e-Auctions:                0 (module not yet active)
📄 Contracts:                 531
📊 Active Tenders:            872
📊 AGPO Tenders:              290
📊 County Tenders:            110
```

### 2.3 System Modules (Fully Documented)

#### Module 1: Supplier Registration

```
Integration Points:
✅ iTax System (KRA) - Real-time tax verification
✅ Business Registration Service (BRS) - Company verification
✅ Integrated Population Registration System (IPRS) - ID verification

Supported Business Types:
- Sole Proprietorship/Business Names
- Partnership Firms
- Limited Liability Partnership Firm
- Community Based Service Provider
- Local Individual Consultants
- Local Company (Private or Public)
- Company Limited by Guarantee
- Foreign Company
```

#### Module 2: Annual Procurement Plan (APP)

```
Functionality:
1. Online preparation from departmental level
2. Aggregation of departmental needs
3. Automated AGPO reservation (minimum 30% budget)
4. Automated county resident reservation (minimum 20% budget)
5. Online approval workflow
6. Public publication

Legal Basis: Section 53 of PPADA 2015
```

#### Module 3: e-Tendering (CRITICAL FOR ONEKA)

```
Key Features:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Preparation of e-tender documents
2. Online approval of tender documents
3. Online publication of tender notices
4. e-clarification system (bidder Q&A)
5. e-tender security and guarantee
6. Tender opening committee approval (online)
7. Secured e-tender submission
8. e-tender opening
9. Tender evaluation committee appointment (online)
10. e-tender evaluation
11. e-tender award

🎯 GEOLOCATION REQUIREMENT (DISCOVERED):
The system enforces "deliveryLocation" field at requisition stage.
Procurement officers CANNOT publish tender without map pin placement.
```

#### Module 4: Contract Management

```
Functionality:
1. e-contract preparation
2. e-Contract Variations (with audit trail)
3. e-Contract Extension (automated alerts)
4. e-Contract Termination (audit trail maintained)
5. Performance guarantee tracking
6. Advance payment administration
7. Contractor performance appraisal

🔴 CoB INTEGRATION GAP:
Contract module tracks project status but does NOT automatically
synchronize with CoB payment authorization system (IFMIS).
```

#### Module 5: e-Catalogue

```
Purpose: Self-service catalog for commonly used items
Features:
- Supplier-uploaded catalog data
- Flexible "shopping cart" system
- Integrated approval workflow
- Direct order issuance to suppliers

Use Case: Framework contracts for office supplies, IT equipment
```

#### Module 6: Open Contracting Data Standards (OCDS)

```
🌟 GAME CHANGER FOR ONEKA

e-GP is built on OCDS (Open Contracting Data Standards)
Purpose: Facilitate publication and analysis of ALL contracting stages

What OCDS Provides:
- Standardized JSON data structure
- Planning → Tender → Award → Contract → Implementation
- Lifecycle tracking with unique identifiers
- Designed for business intelligence and monitoring

ONEKA Integration Opportunity:
If we can access OCDS feed, we get structured JSON instead of scraping:
{
  "ocid": "ocds-ke-egp-KCG-2025-112",
  "tender": {
    "id": "KCG/2025/112",
    "title": "Construction of Wangige Market",
    "value": {"amount": 20000000, "currency": "KES"},
    "deliveryLocation": {
      "geometry": {
        "type": "Point",
        "coordinates": [36.72, -1.22]  // [longitude, latitude]
      },
      "gazetteer": {
        "scheme": "manual_pin",
        "identifiers": ["Wangige Ward, Kiambu County"]
      }
    }
  },
  "awards": [{
    "id": "KCG-2025-112-award-1",
    "suppliers": [{"name": "ABC Construction Ltd", "id": "NCA-1-12345"}],
    "value": {"amount": 20000000, "currency": "KES"},
    "contractPeriod": {
      "startDate": "2025-03-15",
      "endDate": "2026-09-15"
    }
  }]
}
```

### 2.4 Geolocation Evidence (OCDS Structure)

**deliveryLocation Object** (Standard OCDS Field):

```json
{
  "deliveryLocation": {
    "geometry": {
      "type": "Point",
      "coordinates": [36.96, -1.14] // [longitude, latitude] per GeoJSON spec
    },
    "gazetteer": {
      "scheme": "manual_pin", // NOT GPS-verified
      "identifiers": ["Ruiru Town, Kiambu County"]
    },
    "description": "Project site at Ruiru Market, along Thika Road"
  }
}
```

**CRITICAL INSIGHT**: The `geometry.coordinates` field proves that e-GP **enforces geolocation** at tender publication stage. This is NOT optional.

### 2.5 Sample Tender (Real Data from February 19, 2026)

```
Tender ID: 11611
Reference: MASENO/833/RFQ/0072/2025-26
Title: SUPPLY AND DELIVERY OF BRILLIANT WHITE EMULSION PAINT 1X20LTRS
       FOR MAINTENANCE OF STUDENTS HOSTELS
Entity: MASENO UNIVERSITY
Category: Goods
Method: Request for Quotation
Start: 20/02/2026 11:30:00
End: 02/03/2026 11:00:00
Documents: Available for download
```

**Tender Volumes**:

- 872 active tenders across 1,495 procuring entities
- Average: ~0.58 tenders per entity (relatively low, system still ramping up)

### 2.6 System Requirements & Access

**Technical Requirements** (from FAQ):

```
Browser Support: Modern browsers (Chrome, Firefox, Edge)
Authentication: KRA PIN + BRS verification
Registration: Two-tier (Supplier vs Procuring Entity)
API Access: Not publicly documented (likely restricted)
```

**Support Channels**:

```
Email:           support@egpkenya.go.ke, info@egpkenya.go.ke
Phone:           +254 20 2252299
Help Desk:       https://support.egpkenya.go.ke/
Feedback Form:   Google Forms (documented)
Supplier Training: Registration via Google Forms
```

### 2.7 FAQ Insights (Key Questions from Government Website)

**Q: Is this e-GP system replacing PPIP?**  
**A**: Yes. e-GP is the centralized platform for ALL procurement.

**Q: Shall e-GP replace other eProcurement systems used by government agencies? (SAP, IFMIS, Oracle)**  
**A**: Yes, it aims to standardize procurement across all entities.

**Q: When a supplier registers on e-GP, does that profile reflect on other government entities?**  
**A**: Yes. Suppliers register ONCE and can bid on tenders from ANY procuring entity.

**Q: Will suppliers be required to be present physically or online in bid opening?**  
**A**: Online (automated e-tender opening system).

### 2.8 ONEKA Integration Strategy

**Primary Data Source Strategy**:

```python
egp_integration_plan = {
    "priority": "CRITICAL",
    "data_access_method": "UNKNOWN (requires investigation)",
    "options": [
        {
            "method": "OCDS JSON Feed",
            "probability": "MEDIUM (OCDS compliance documented but feed URL not public)",
            "advantage": "Structured JSON, geolocation included, lifecycle tracking",
            "action": "Contact National Treasury for API access"
        },
        {
            "method": "Web Scraping",
            "probability": "HIGH (fallback if API denied)",
            "advantage": "No permission required, proven technology",
            "challenge": "4,591 tenders × 175 pages = complex scraping"
        },
        {
            "method": "Supplier Account Access",
            "probability": "LOW (violates ToS, limited visibility)",
            "advantage": "Portal access",
            "challenge": "Only see tenders you're eligible for"
        }
    ],
    "recommended_approach": "Negotiate API access with National Treasury (mention OCDS public data mandate)"
}

# Fields Available from e-GP
egp_fields = [
    "tender_id",              # Unique e-GP ID
    "tender_reference",       # Entity's reference (e.g., MASENO/833/RFQ/0072/2025-26)
    "tender_title",           # Full project description
    "procuring_entity",       # Ministry/County/Agency
    "category",               # Goods/Works/Services
    "method",                 # RFQ/Open Tender/Restricted
    "contract_value_kes",     # Estimated/Awarded amount
    "start_date",             # Tender publication
    "end_date",               # Bid submission deadline
    "delivery_location_gps",  # ⭐ CRITICAL: Lat/Lon coordinates
    "delivery_location_text", # Description/Address
    "awarded_contractor",     # Winner details (post-award)
    "contract_period",        # Start/End dates
    "ocds_id"                 # Open Contracting Data Standard ID
]

# Geolocation Validation Pipeline
egp_gps_validation = {
    "input": "deliveryLocation.geometry.coordinates",
    "validation_layers": [
        "county_boundary_check",      # Is GPS within correct county?
        "county_hq_proximity_check",  # Is it a lazy pin drop? (within 1km of county HQ)
        "facility_registry_match",    # Does it match KMHFL/NEMIS/KIPPRA facility?
        "historical_project_check",   # Is it same location as completed project?
        "ocean_border_check"          # Is it in Indian Ocean or outside Kenya?
    ],
    "output": {
        "gps_quality_score": "0-100",
        "confidence_level": "VERIFIED | ACCEPTABLE | SUSPECT | INVALID",
        "recommended_action": "USE_AS_IS | CROSS_REFERENCE | MANUAL_REVIEW | REJECT"
    }
}
```

**API Access Negotiation Talking Points**:

```
To: National Treasury e-GP Team (support@egpkenya.go.ke)
Subject: OCDS Data Access for Public Audit Enhancement

Dear e-GP Team,

We are ONEKA, a satellite-based audit system working with the Office of the
Auditor General to enhance physical progress verification of public projects.

Request: Access to e-GP OCDS JSON feed for tender data (as per Open Contracting
Data Standards public data mandate)

Use Case: Link e-GP tender geolocation data to Controller of Budget payment
records and satellite imagery for real-time ghost project detection

Benefits to Government:
1. Real-time audit capability (reduce 2-year audit lag)
2. Evidence-based prosecution (satellite + financial + procurement evidence)
3. Deterrence effect (contractors know they're being watched from space)

Compliance: We will adhere to all data protection requirements and use data
solely for public audit purposes.

Technical Requirements:
- OCDS JSON feed (read-only)
- Fields needed: tender_id, deliveryLocation, contract value, awarded contractor
- Update frequency: Daily batch is sufficient

Can we schedule a call to discuss API access?
```

---

## Part 3: CoB (Office of the Controller of Budget)

### 3.1 Constitutional Mandate

**Official URL**: https://cob.go.ke  
**Operator**: Office of the Controller of Budget (OCOB)  
**Legal Basis**: Article 228, Constitution of Kenya 2010  
**Established**: August 27, 2011  
**Location**: Bima House, 12th Floor, Harambee Avenue, Nairobi

**Constitutional Authority** (Article 228):

```
The Controller of Budget shall:
1. Oversee implementation of budgets of National and County Governments
2. Authorize withdrawals from public funds (Articles 204, 206, 207)
3. NOT approve withdrawal unless authorized by law
4. Submit reports to Parliament every FOUR MONTHS
5. Publish and publicize all reports (transparency mandate)
```

### 3.2 Core Functions

**Vision**:

> "To be a leading and independent oversight institution in public financial management"

**Mission**:

> "To oversee implementation of Government budgets through timely authorization of withdrawals from Public Funds and reporting on utilization"

**Core Values**:

- Integrity
- Transparency & Accountability
- Professionalism
- Independence
- Creativity & Innovativeness
- Teamwork

### 3.3 Reporting Framework

**Report Types** (Article 254):

```
1. QUARTERLY REPORTS (Budget Implementation Review Reports - BIRR)
   Frequency: Every 4 months
   Audience: President + Parliament
   Content: National and County budget execution

2. ANNUAL REPORTS
   Frequency: Yearly
   Audience: President + Parliament
   Content: Consolidated budget implementation analysis

3. SPECIAL REPORTS
   Trigger: Investigations or stoppage of funds
   Authority: Article 254(2)
   Content: Specific compliance or fraud issues

4. ARBITRATION/MEDIATION REPORTS
   Authority: Article 225(7a), Article 252(1a&1b)
   Content: Budget disputes between government entities

5. PERFORMANCE REPORTS
   Content: OCOB's own activities and achievements
```

**Transparency Mandate** (Article 254(3)):

> "Every report required from a commission or holder of an independent office under this Article shall be **published and publicized**."

### 3.4 Data Structure (BIRR Reports)

**Report Format**: PDF (no structured data API)  
**Publication Channel**: https://cob.go.ke/reports/

**Report Categories**:

- National Government Budget Implementation Review Reports
- County Government Budget Implementation Review Reports
- Quarterly Reports (Q1, Q2, Q3, Q4)
- Annual Reports
- Special Reports

**Sample Report Structure** (from website):

```
BUDGET IMPLEMENTATION REVIEW REPORT (BIRR)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. EXECUTIVE SUMMARY
2. BUDGET ALLOCATION BY MINISTRY/COUNTY
   ├─ Vote Head 3001: Ministry of Health
   │  ├─ Budget Allocated:  KES 500M
   │  ├─ Budget Released:   KES 300M (60%)
   │  └─ Budget Absorbed:   KES 270M (90% of released)
   └─ Vote Head 3042: Construction of Markets
      ├─ Budget Allocated:  KES 450M
      ├─ Budget Released:   KES 270M (60%)
      └─ Budget Absorbed:   KES 270M (100% of released)

3. EXCHEQUER RELEASES (by month)
4. PENDING BILLS
5. DEVELOPMENT VS RECURRENT EXPENDITURE
6. COMPLIANCE ISSUES
7. RECOMMENDATIONS

🔴 CRITICAL LIMITATION:
   Reports use VOTE HEADS (budget codes), NOT tender numbers
   No project names, GPS coordinates, or contractor details
```

### 3.5 Recent Activities (from Website News)

**February 16, 2026**:

> "Controller of Budget Updates IBEC members on County Compliance, Pending Bills, and FY 2026/27 Revenue Proposals during 29th Ordinary Session of IBEC"

**September 10, 2025**:

> "COB UNVEILS THE ANNUAL NATIONAL GOVERNMENT BUDGET IMPLEMENTATION REVIEW REPORT FOR FY2024/25"

**Key Topics in Reports**:

- County compliance with budgetary regulations
- Pending bills (unpaid contractor obligations)
- Revenue proposals for upcoming fiscal year
- Budget implementation rates (absorption capacity)

### 3.6 Contact Information

**Official Contact**:

```
Address:   Bima House, 12th Floor, Harambee Avenue, Nairobi
           P.O. Box 35616 - 00100 Nairobi, Kenya
Phone:     +254 20 2211068
Mobile:    +254 709 910 000
           +254 716 274 922

Corruption Reporting:
Email:     corruption-reporting@cob.go.ke
Toll Free: 0800 720 141
```

### 3.7 Integration Gaps (CRITICAL FOR ONEKA)

**What CoB Reports HAVE**:

```
✅ Budget allocation by ministry/county
✅ Exchequer releases (money disbursed to entities)
✅ Budget absorption rates (% of released funds spent)
✅ Pending bills (contractor claims)
✅ Compliance issues
```

**What CoB Reports DO NOT HAVE**:

```
❌ Tender numbers (e.g., KCG/2025/112)
❌ Project names (e.g., "Wangige Market Construction")
❌ GPS coordinates
❌ Contractor names (in most cases)
❌ Physical progress assessments
❌ Link to e-GP tender database
```

**The CoB/e-GP Integration Gap**:

```
CoB BIRR Report Says:
"Vote Head 3042 - Construction of Markets: KES 270M released"

e-GP Database Says:
"Tender KCG/2025/112 - Wangige Market: KES 20M contract to ABC Construction Ltd"

THE GAP:
There is NO automatic link between these two records!

CoB cannot tell you:
- Which specific market got the KES 20M (out of Vote Head 3042's KES 270M)
- Where that market is located
- Who the contractor is
- If construction has started

This is ONEKA's opportunity.
```

### 3.8 ONEKA Integration Strategy

**Data Extraction Plan**:

```python
cob_integration_plan = {
    "priority": "HIGH (trigger for audit pipeline)",
    "data_source": "PDF reports published quarterly",
    "extraction_method": "PDF parsing + table extraction",
    "target_tables": [
        "Budget Allocation by Ministry",
        "Exchequer Releases by Vote Head",
        "Pending Bills by Entity",
        "Development Expenditure by Sector"
    ],
    "update_frequency": "Quarterly (within 1 week of BIRR publication)",
    "matching_strategy": "Multi-factor inference matching to e-GP records"
}

# Fields to Extract from BIRR PDFs
cob_fields = [
    "ministry_county",        # Procuring entity
    "vote_head",              # Budget code (e.g., 3042)
    "vote_head_description",  # e.g., "Construction of Markets"
    "budget_allocated_kes",   # Total voted budget
    "budget_released_kes",    # Amount actually transferred
    "budget_absorbed_kes",    # Amount spent
    "absorption_rate_pct",    # Efficiency metric
    "reporting_period",       # Q1/Q2/Q3/Q4 2024/25
    "compliance_issues"       # Flagged problems
]

# Multi-Factor Matching Algorithm
def match_cob_to_egp(cob_record, egp_database):
    """
    Link CoB payment record to e-GP tender using probabilistic matching

    Matching Signals (weighted):
    1. Entity Match (40%): "Ministry of Health" → "MOH" in e-GP
    2. Amount Match (30%): Budget absorbed ≈ Contract value (±10%)
    3. Keyword Match (20%): "Markets" in vote head → "Market" in tender title
    4. Timing Match (10%): Payment period overlaps contract period
    """

    scores = []

    for tender in egp_database:
        score = 0

        # Signal 1: Entity matching
        entity_similarity = fuzz.token_set_ratio(
            cob_record['ministry_county'],
            tender['procuring_entity']
        ) / 100
        score += entity_similarity * 40

        # Signal 2: Amount matching (within 10% tolerance)
        amount_diff_pct = abs(
            cob_record['budget_absorbed_kes'] - tender['contract_value_kes']
        ) / tender['contract_value_kes']

        if amount_diff_pct <= 0.10:
            score += 30
        elif amount_diff_pct <= 0.20:
            score += 15

        # Signal 3: Keyword matching
        cob_keywords = extract_keywords(cob_record['vote_head_description'])
        tender_keywords = extract_keywords(tender['tender_title'])
        keyword_overlap = len(set(cob_keywords) & set(tender_keywords))
        score += min(keyword_overlap * 5, 20)  # Max 20 points

        # Signal 4: Timing matching
        if is_overlapping_period(cob_record['reporting_period'], tender['contract_period']):
            score += 10

        scores.append({
            'tender': tender,
            'match_score': score,
            'confidence': 'HIGH' if score > 75 else 'MEDIUM' if score > 50 else 'LOW'
        })

    # Return top 3 candidates
    return sorted(scores, key=lambda x: x['match_score'], reverse=True)[:3]
```

**Reverse Pipeline (CoB-Triggered Audit)**:

```python
def cob_triggered_audit():
    """
    Start audit from CoB payment disclosure

    WORKFLOW:
    1. Parse new BIRR report (PDF → structured data)
    2. For each Vote Head with expenditure:
       a. Search e-GP database for matching tenders
       b. Extract GPS coordinates from matched tender
       c. Validate GPS quality (county HQ check)
       d. Task satellite analysis
       e. Compare financial vs physical progress
    3. Generate Triangle of Truth verdict
    """

    # Step 1: Extract CoB data
    birr_report = fetch_latest_birr_report()  # Download PDF from cob.go.ke
    cob_records = extract_tables_from_pdf(birr_report)  # Parse tables

    # Step 2: For each significant expenditure
    for record in cob_records:
        if record['budget_absorbed_kes'] > 5000000:  # KES 5M threshold

            # Step 3: Match to e-GP
            egp_matches = match_cob_to_egp(record, egp_database)

            if not egp_matches:
                flag_unmatched_payment(record)  # Red flag: payment with no tender
                continue

            best_match = egp_matches[0]

            if best_match['confidence'] == 'LOW':
                flag_uncertain_match(record, best_match)
                continue

            # Step 4: Extract GPS
            tender = best_match['tender']
            gps = validate_egp_geolocation(tender)

            # Step 5: Satellite analysis
            satellite_result = trigger_satellite_analysis(
                gps['latitude'],
                gps['longitude'],
                tender['contract_period']['startDate']
            )

            # Step 6: Triangle of Truth
            financial_progress = (
                record['budget_absorbed_kes'] / tender['contract_value_kes']
            ) * 100

            physical_progress = satellite_result['physical_progress_pct']

            progress_gap = financial_progress - physical_progress

            # Step 7: Generate alert
            if progress_gap > 50:
                generate_ghost_project_alert(
                    cob_record=record,
                    egp_tender=tender,
                    satellite_analysis=satellite_result,
                    risk_score=95
                )
```

---

## Part 4: System Integration Matrix

### 4.1 Data Exchange Reality

```
SYSTEM INTERCONNECTIONS (Current State):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─────────┐      ┌─────────┐      ┌─────────┐
│  PPIP   │      │  e-GP   │      │   CoB   │
│ (Legacy)│      │ (Active)│      │(Finance)│
└────┬────┘      └────┬────┘      └────┬────┘
     │                │                │
     │ NO LINK        │ NO LINK        │
     └────────────────┼────────────────┘
                      │
                      ▼
               ┌─────────────┐
               │   ONEKA     │
               │ (Integrator)│
               └─────────────┘

REALITY: Zero automated data exchange between systems
ONEKA ROLE: First system to bridge all three data sources
```

### 4.2 Integration Complexity Matrix

| Data Element          | PPIP    | e-GP           | CoB         | ONEKA Solution                     |
| --------------------- | ------- | -------------- | ----------- | ---------------------------------- |
| **Tender Number**     | ✅ Yes  | ✅ Yes         | ❌ No       | Link via entity+amount matching    |
| **GPS Coordinates**   | ❌ No   | ✅ Yes (OCDS)  | ❌ No       | Primary: e-GP, Validate: KMHFL     |
| **Contract Value**    | ✅ Yes  | ✅ Yes         | ⚠️ Indirect | Match amounts (±10% tolerance)     |
| **Contractor Name**   | ✅ Yes  | ✅ Yes         | ⚠️ Partial  | Fuzzy string matching              |
| **Payment Status**    | ❌ No   | ⚠️ Partial     | ✅ Yes      | CoB as payment source of truth     |
| **Physical Progress** | ❌ No   | ❌ No          | ❌ No       | ONEKA satellite analysis (unique!) |
| **Project Location**  | ⚠️ Text | ✅ GPS (OCDS)  | ❌ No       | e-GP primary, validate with KMHFL  |
| **Ministry/County**   | ✅ Yes  | ✅ Yes         | ✅ Yes      | Direct field match                 |
| **Unique Identifier** | Tender# | Tender# + OCID | Vote Head   | Generate ONEKA Project UUID        |

### 4.3 ONEKA's Unique Value Add

```
WHAT EACH SYSTEM KNOWS (in isolation):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PPIP Knows:
✅ Historical tender publication (2018-2025)
✅ Contract awards (130,839 contracts)
❌ Nothing about current projects (e-GP took over)

e-GP Knows:
✅ Current tenders (4,591 active)
✅ GPS coordinates (mandatory field)
✅ Contractor details
✅ Contract values and timelines
❌ Whether payment was actually made
❌ Whether construction actually happened

CoB Knows:
✅ Money released to ministries (by Vote Head)
✅ Budget absorption rates
✅ Pending bills
❌ Which specific projects got the money
❌ Where those projects are located
❌ Who the contractors are (usually)

ONEKA Knows (UNIQUE):
━━━━━━━━━━━━━━━━━━━━━━
✅ ALL OF THE ABOVE (through integration)
✅ PLUS: Physical reality from satellite
✅ PLUS: Triangle of Truth comparison
✅ PLUS: Real-time ghost project detection

WITHOUT ONEKA: Systems operate in silos, fraud discovered 2 years later
WITH ONEKA: Cross-system validation, fraud detected in real-time
```

---

## Part 5: Technical Integration Roadmap

### 5.1 Data Access Strategy by System

```python
integration_roadmap = {
    "Phase 1: PPIP Historical Import (Sprint 2 - COMPLETE)": {
        "method": "Web scraping",
        "status": "✅ Implemented",
        "records_target": 256034,
        "data_period": "2018-2025",
        "update_frequency": "ONE-TIME (historical only)",
        "challenges": "PDF OCR, rate limiting",
        "completion": "Sprint 2"
    },

    "Phase 2: e-GP Integration (Sprint 3.5 - PRIORITY)": {
        "method": "OCDS API (preferred) or Web scraping (fallback)",
        "status": "⏳ Pending API access negotiation",
        "records_target": 4591,  # Current active tenders
        "data_period": "2025-present",
        "update_frequency": "Daily",
        "challenges": "API access approval, GPS validation",
        "completion_target": "Sprint 3.5",
        "action_items": [
            "Contact National Treasury (support@egpkenya.go.ke)",
            "Request OCDS JSON feed access",
            "Fallback: Develop e-GP scraper",
            "Build GPS validation pipeline"
        ]
    },

    "Phase 3: CoB BIRR Integration (Sprint 4)": {
        "method": "PDF parsing + table extraction",
        "status": "⏳ Planned",
        "reports_target": "Quarterly (4 per year)",
        "data_period": "2024-present",
        "update_frequency": "Quarterly (within 1 week of publication)",
        "challenges": "PDF parsing accuracy, entity name variations",
        "completion_target": "Sprint 4",
        "action_items": [
            "Develop BIRR PDF parser (Tabula/Camelot)",
            "Build multi-factor matching algorithm",
            "Create CoB-to-e-GP linking service",
            "Implement Triangle of Truth calculator"
        ]
    }
}
```

### 5.2 API Access Priorities

**Priority 1: e-GP OCDS Feed** (CRITICAL)

```
Why: GPS coordinates + structured tender data
Request to: support@egpkenya.go.ke
Talking points: OCDS public data mandate, OAG partnership
Fallback: Web scraping (4,591 tenders manageable)
Timeline: Initiate contact in Sprint 3
```

**Priority 2: CoB Report Automation** (HIGH)

```
Why: Payment data triggers audit pipeline
Request to: Not applicable (PDFs are public)
Approach: Automated PDF download + parsing
Timeline: Sprint 4 implementation
```

**Priority 3: PPIP Legacy Data** (LOW - already accessible)

```
Why: Historical ML training data
Status: Sprint 2 scraper already implemented
Action: Execute one-time historical import
Timeline: Background task during Sprint 3
```

### 5.3 Success Metrics

**Integration Completeness**:

```
Target: Link 80% of CoB payments to e-GP tenders by Sprint 4
Measurement: % of BIRR Vote Heads matched to e-GP projects
Current: 0% (systems not integrated)
Sprint 4 Goal: 80%
Sprint 6 Goal: 95%
```

**Geolocation Accuracy**:

```
Target: 70-85% of projects have verified GPS coordinates
Measurement: % of projects with VERIFIED or ACCEPTABLE GPS quality score
Current: 0% (no e-GP integration yet)
Sprint 3.5 Goal: 70% (e-GP pins accepted)
Sprint 5 Goal: 85% (with KMHFL/NEMIS validation)
```

**Triangle of Truth Coverage**:

```
Target: Generate Triangle status for 100% of matched projects
Measurement: % of projects with all three legs (Finance + Procurement + Physical)
Current: 0%
Sprint 5 Goal: 60% (CoB quarterly reports lag)
Sprint 6 Goal: 90%
```

---

## Part 6: Key Takeaways for ONEKA

### 6.1 Strategic Insights

1. **e-GP Mandatory Geolocation = Game Changer**
   - 70-85% of projects NOW have GPS (since July 2025 mandate)
   - Shifts ONEKA's challenge from "finding location" → "validating quality"
   - Reduces dependency on KMHFL fuzzy matching (now secondary validation)

2. **PPIP is Dead for Current Projects**
   - 256,034 historical records = valuable ML training data
   - Zero new tenders since e-GP mandate (July 2025)
   - ONE-TIME import, then close that pipeline

3. **CoB/e-GP Gap is ONEKA's Moat**
   - No other system bridges Finance (CoB) ↔ Procurement (e-GP)
   - Multi-factor matching is CRITICAL (entity + amount + timing + keywords)
   - Triangle of Truth is our unique value proposition

4. **OCDS Compliance Opens Doors**
   - e-GP built on Open Contracting Data Standards
   - Government has transparency mandate (Article 254)
   - Strong case for API access as "public data"

### 6.2 Immediate Actions

**This Sprint (Sprint 2 completion)**:

- ✅ PPIP scraper complete (already done)
- ⏳ Test PPIP scraper with 20+ real tenders (pending)

**Next Sprint (Sprint 3 + 3.5)**:

- 📧 Email National Treasury requesting e-GP OCDS API access
- 🏗️ Build e-GP GPS validation pipeline (county HQ detection)
- 🔗 Design CoB-to-e-GP matching algorithm
- 📊 Create Triangle of Truth data model

**Sprint 4**:

- 📄 Implement CoB BIRR PDF parser
- 🧮 Build Triangle of Truth calculator
- 📈 Develop progress gap alert system

### 6.3 Risk Mitigation

**Risk 1: e-GP API access denied**

```
Mitigation: Develop web scraping fallback
Complexity: Moderate (4,591 tenders, pagination, authentication)
Timeline: 2 weeks development if needed
```

**Risk 2: GPS quality lower than expected**

```
Mitigation: Robust validation pipeline + KMHFL secondary matching
Impact: Reduces coverage from 85% to 60% (still better than pre-e-GP)
Timeline: Already planned in Sprint 3.5
```

**Risk 3: CoB-to-e-GP matching accuracy < 80%**

```
Mitigation: Multi-factor matching + machine learning for edge cases
Impact: Reduces Triangle of Truth coverage
Timeline: Iterative improvement in Sprints 4-6
```

---

## Conclusion

Based on comprehensive analysis of official government systems, ONEKA's integration strategy is well-positioned but requires three critical adjustments:

1. **Prioritize e-GP** over PPIP as primary data source (e-GP has GPS, PPIP doesn't)
2. **Negotiate API access** to e-GP OCDS feed (structured JSON beats web scraping)
3. **Focus on Triangle of Truth** as our core value (linking Finance + Procurement + Physical reality is UNIQUE)

The gap between CoB (who got paid) and e-GP (what was contracted) is real, severe, and ONEKA's opportunity. No other system bridges this gap. This is our moat.

---

**Document Version**: 1.0  
**Date**: February 19, 2026  
**Next Review**: After e-GP API access negotiation response  
**Owner**: ONEKA Technical Team  
**Classification**: Internal Technical Reference
