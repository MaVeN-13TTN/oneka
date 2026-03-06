# Ghost Project Classifier — Performance Report

**Model version:** `v1`
**Training samples:** 30 (10 ghost, 20 success)
**CV strategy:** 5-fold StratifiedKFold
**SMOTE applied:** Yes
**Overall status:** **FAIL**

---

## Cross-Validation Metrics

| Metric | Score | Target | Met? |
|---|---|---|---|
| AUC (ROC) | 0.5625 | ≥ 0.80 | No ✗ |
| Precision (ghost) | 0.3667 | ≥ 0.75 | No ✗ |
| Recall (ghost) | 0.4000 | ≥ 0.70 | No ✗ |
| F1 (ghost) | 0.3467 | — | — |

---

## Feature Importances

              feature  importance
   contract_value_log    0.431349
 project_type_encoded    0.294447
    county_cloud_risk    0.274204
           ndvi_slope    0.000000
sar_backscatter_delta    0.000000
     divergence_score    0.000000
   absorption_anomaly    0.000000
   months_to_clearing    0.000000
      contractor_tier    0.000000
    phase_on_schedule    0.000000

---

## Notes

- At training time, the labelled CSV contains only `budget_kes`, `project_name`,
  `county`, `award_date`, and `completion_date`. All satellite and financial features
  (`ndvi_slope`, `sar_backscatter_delta`, `divergence_score`, `months_to_clearing`,
  `absorption_anomaly`, `contractor_tier`, `phase_on_schedule`) are NaN and imputed
  with column medians by the pipeline.
- As Sentinel-2/SAR scenes accumulate in `satellite_analyses`, retrain with full
  features to substantially improve AUC.
- Artefacts:
  - `satellite/models/ghost_detector_v1.pkl`
  - `satellite/models/confusion_matrix.png`
  - `satellite/models/roc_curve.png`
  - `satellite/models/model_metrics.json`
