# Training Data Collection Plan

## Overview

This document outlines the strategy for collecting a comprehensive satellite training dataset to train the ONEKA AI ghost project detection model.

## Dataset Specifications

### Target Size

**Projects:** 30 historical infrastructure projects

- 20 successful/completed projects
- 10 ghost/abandoned/fraud projects

**Temporal Coverage:** Monthly imagery from award date to completion date (or present for ghost projects)

**Expected Data Volume:**

- Average project duration: 24 months
- 30 projects × 24 months = **720 satellite observations**
- 2 sensors (Sentinel-1 + Sentinel-2) = **1,440 scenes total**

### Data Sources

| Source         | Product         | Purpose                           | Scenes per Project |
| -------------- | --------------- | --------------------------------- | ------------------ |
| Sentinel-2 L2A | Optical NDVI    | Vegetation clearing detection     | 24 (monthly)       |
| Sentinel-1 GRD | SAR backscatter | Structure emergence (all-weather) | 24 (monthly)       |

## Project Selection Criteria

### Successful Projects (20 required)

**Sources:**

1. Office of the Auditor General (OAG) Annual Reports
2. County government project databases
3. Kenya Master Health Facility List (KMHFL) - for health facilities
4. Ministry of Education school census
5. KeNHA completed roads database

**Selection Requirements:**

- ✅ Construction confirmed complete (OAG field audit or photos)
- ✅ GPS coordinates available or geocodable facility name
- ✅ Award date and completion date documented
- ✅ Budget amount known
- ✅ Project type: health, education, roads, water, or administrative buildings

**Diversity Requirements:**
| Category | Target Count | Rationale |
|----------|--------------|-----------|
| Urban projects | 8 | Test model on different land cover |
| Rural projects | 8 | Different baseline vegetation |
| Mixed/peri-urban | 4 | Edge cases |
| Health facilities | 6 | High-value targets for fraud |
| Education facilities | 6 | Common project type |
| Roads | 4 | Linear infrastructure |
| Water/admin | 4 | Diverse construction patterns |

### Ghost Projects (10 required)

**Sources:**

1. EACC (Ethics & Anti-Corruption Commission) prosecution records
2. OAG special audit reports flagging fraud
3. County investigative reports
4. Public Investments Committee (PIC) reports
5. Investigative journalism (e.g., Daily Nation exposés)

**Selection Requirements:**

- ✅ Confirmed as ghost/fraud (legal judgment, EACC report, or OAG audit)
- ✅ GPS coordinates or matchable facility name
- ✅ Award date documented
- ✅ Budget amount known
- ✅ Evidence of fund disbursement (confirms it's a ghost, not just cancelled)

**Ghost Project Categories:**

- **Type A (4 projects):** No construction started (funds embezzled)
- **Type B (3 projects):** Partial construction, then abandoned
- **Type C (3 projects):** Substandard construction (collapses, demolitions)

## Data Collection Timeline

### Phase 1: Project Identification (Week 1)

**Tasks:**

- [ ] Compile list of 30 projects from OAG/EACC reports
- [ ] Extract metadata: name, location, dates, budget
- [ ] Geocode projects (KMHFL matching or manual coordinate lookup)
- [ ] Validate GPS coordinates (Google Earth visual check)
- [ ] Create `training_projects.csv`

**Deliverable:** CSV file with 30 projects

### Phase 2: Satellite Data Download (Week 2-3)

**Tasks:**

- [ ] For each project, download monthly Sentinel-2 scenes
- [ ] For each project, download monthly Sentinel-1 scenes
- [ ] Filter scenes by cloud cover (< 30%)
- [ ] Organize downloads by project and date
- [ ] Verify all scenes downloaded successfully

**Download Strategy:**

- Use `sentinelsat` Python library for batch downloads
- Parallelize downloads (2 concurrent connections)
- Estimate: 1,440 scenes × 10 min/scene ÷ 2 parallel = **120 hours = 5 days**

**Deliverable:** 1,440 downloaded satellite scenes

### Phase 3: Processing & Feature Extraction (Week 4-5)

**Tasks:**

- [ ] Process all Sentinel-2 scenes (NDVI calculation)
- [ ] Process all Sentinel-1 scenes (SAR backscatter)
- [ ] Extract monthly statistics for each project
- [ ] Create time-series CSVs
- [ ] Generate visualizations for manual QC

**Processing Strategy:**

- Parallelize processing (4 CPU cores)
- Estimate: 1,440 scenes × 5 min/scene ÷ 4 cores = **30 hours = 1.25 days**

**Deliverable:**

- 1,440 processed GeoTIFFs
- 30 NDVI time-series CSVs
- 30 SAR time-series CSVs

### Phase 4: Manual Labeling & QC (Week 6)

**Tasks:**

- [ ] Visual inspection of all 30 project time-series
- [ ] Annotate construction phases manually
- [ ] Identify anomalies (cloud contamination, seasonal flooding)
- [ ] Cross-validate labels against OAG/EACC reports
- [ ] Create label JSON files

**Manual Annotation Categories:**

1. **Pre-construction:** Vegetation intact, no clearing
2. **Land clearing:** NDVI drop, bare soil visible
3. **Foundation:** Low NDVI, SAR backscatter stable
4. **Superstructure:** SAR backscatter increase (vertical structures)
5. **Completion:** Stable SAR, partial NDVI recovery (landscaping)
6. **Abandonment:** NDVI recovery > 50%, no SAR change

**Deliverable:** 30 labeled JSON files

## Feature Engineering Plan

### NDVI-Based Features (7 features)

| Feature               | Calculation                       | Example Value |
| --------------------- | --------------------------------- | ------------- |
| `ndvi_initial`        | Baseline NDVI at award date       | 0.62          |
| `ndvi_final`          | Current/completion NDVI           | 0.18          |
| `ndvi_max_drop`       | Maximum single-month drop         | 0.55          |
| `ndvi_slope`          | Linear regression slope over time | -0.023        |
| `ndvi_recovery_ratio` | (final - min) / (initial - min)   | 0.08          |
| `clearing_detected`   | Binary: drop > 0.15 threshold     | True          |
| `months_to_clearing`  | Months from award to first drop   | 2             |

### SAR-Based Features (4 features)

| Feature              | Calculation                       | Example Value |
| -------------------- | --------------------------------- | ------------- |
| `sar_initial`        | Baseline VV backscatter at award  | -15.2 dB      |
| `sar_final`          | Current/completion VV backscatter | -8.4 dB       |
| `sar_increase`       | final - initial                   | 6.8 dB        |
| `structure_detected` | Binary: increase > 3 dB threshold | True          |

### Temporal Features (2 features)

| Feature         | Calculation                       | Example Value |
| --------------- | --------------------------------- | ------------- |
| `months_active` | Award to completion/current       | 24            |
| `progress_gap`  | Expected % - Estimated physical % | -5            |

### Metadata Features (2 features)

| Feature              | Calculation                           | Example Value |
| -------------------- | ------------------------------------- | ------------- |
| `contract_value_log` | log10(budget_kes)                     | 19.67         |
| `project_type`       | One-hot: health/education/roads/water | [1,0,0,0]     |

**Total Features:** 15

## Quality Control Procedures

### Automated QC Checks

```python
def quality_check_scene(scene_metadata):
    """
    Automated quality checks for satellite scenes.
    """
    checks = {
        "valid_coordinates": -90 <= lat <= 90 and -180 <= lon <= 180,
        "cloud_cover_acceptable": cloud_cover < 30,
        "valid_pixels_sufficient": valid_pixels_pct > 80,
        "ndvi_range_valid": -1.0 <= ndvi_mean <= 1.0,
        "sar_range_valid": -30 <= sar_vv_mean <= 5,
        "no_data_gaps": len(missing_months) == 0,
    }

    return all(checks.values()), checks
```

### Manual QC Checklist

For each project:

- [ ] Visual confirmation: baseline scene shows pre-construction state
- [ ] Visual confirmation: final scene shows completed/abandoned state
- [ ] Time-series plot is smooth (no sudden jumps from cloud contamination)
- [ ] NDWI check: no seasonal flooding false positives
- [ ] Cross-reference: construction phase matches OAG report timeline
- [ ] GPS accuracy: coordinates within 500m of actual facility

## Data Storage Estimates

### Raw Satellite Data

- Sentinel-2 L2A: 1 GB per scene (compressed)
- Sentinel-1 GRD: 1.2 GB per scene
- Total raw: **1,440 scenes × 1.1 GB average = 1.6 TB**

**Storage Strategy:**

- Keep raw data for 7 days during processing
- Delete after processed GeoTIFFs validated
- Archive 10% of scenes to S3 Glacier for audit trail

### Processed Data

- NDVI GeoTIFF: 50 MB per scene
- SAR GeoTIFF (VV + VH): 100 MB per scene
- Visualizations: 2 MB per scene
- Total processed: **1,440 × 150 MB = 216 GB**

**Storage Strategy:**

- Keep indefinitely on local disk
- Sync to S3 Standard (monthly backup)

### Training Dataset

- Time-series CSVs: 30 projects × 2 files × 50 KB = **3 MB**
- Feature JSONs: 30 projects × 10 KB = **300 KB**
- Labels: 30 projects × 2 KB = **60 KB**
- Total training: **< 5 MB**

**Storage Strategy:**

- Keep in GitHub repository
- Export to S3 for ML training pipeline

## Labeling Strategy

### Ground Truth Sources

| Project Type | Label Source                                           | Confidence |
| ------------ | ------------------------------------------------------ | ---------- |
| Successful   | OAG audit report + field photos                        | High       |
| Successful   | Google Street View (dated)                             | Medium     |
| Successful   | KMHFL database (facility operational)                  | High       |
| Ghost        | EACC prosecution record                                | High       |
| Ghost        | OAG special audit (funds unaccounted)                  | High       |
| Ghost        | Investigative journalism + no facility on Google Earth | Medium     |

### Labeling Workflow

```python
def label_project(project_id):
    """
    Interactive labeling tool.
    """
    # Load time-series data
    ndvi_ts = pd.read_csv(f"data/training/time_series/{project_id}_ndvi.csv")
    sar_ts = pd.read_csv(f"data/training/time_series/{project_id}_sar.csv")

    # Plot time-series
    plot_timeseries(ndvi_ts, sar_ts)

    # Manual input
    label = input("Enter label (success/ghost): ")
    construction_started = input("Construction started? (yes/no): ")
    construction_completed = input("Construction completed? (yes/no): ")

    # Save label
    label_data = {
        "project_id": project_id,
        "label": label,
        "construction_started": construction_started == "yes",
        "construction_completed": construction_completed == "yes",
        "annotator": "ML_Engineer",
        "date": datetime.now().isoformat()
    }

    with open(f"data/training/labels/{project_id}_label.json", "w") as f:
        json.dump(label_data, f, indent=2)
```

## Expected Challenges & Mitigation

| Challenge                                                        | Impact                         | Mitigation                           |
| ---------------------------------------------------------------- | ------------------------------ | ------------------------------------ |
| Cloud cover > 30% for some months                                | Missing data points            | Use SAR (cloud-free) or interpolate  |
| GPS coordinates inaccurate                                       | Wrong AOI analyzed             | Manual verification on Google Earth  |
| OAG reports lack precise dates                                   | Can't align satellite timeline | Use fiscal year quarters as estimate |
| Seasonal flooding false positives                                | Ghost projects misclassified   | Apply NDWI filter                    |
| Construction type not visible from space (underground pipelines) | No NDVI/SAR change             | Exclude from training set            |

## Success Metrics

**Dataset Quality Targets:**

- [ ] All 30 projects have monthly data for 80%+ of project duration
- [ ] Cloud cover < 30% for 80%+ of Sentinel-2 scenes
- [ ] No data gaps > 3 consecutive months
- [ ] Manual QC pass rate: 90%+
- [ ] Label agreement with OAG reports: 100%

**Model Performance Targets:**

- Accuracy: 80-85%
- Precision (ghost detection): 75-80%
- Recall (ghost detection): 80-85%
- F1 Score: 77-82%

## Next Steps (Sprint 2)

1. Download full training dataset (1,440 scenes)
2. Process all scenes (NDVI + SAR)
3. Complete manual labeling
4. Train Random Forest model
5. Validate on hold-out test set
6. Deploy model to production API

---

**Status:** Planning Phase  
**Owner:** ML/Satellite Engineer  
**Last Updated:** February 9, 2026  
**Version:** 1.0
