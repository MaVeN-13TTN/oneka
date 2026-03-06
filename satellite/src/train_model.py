"""
Training pipeline for the Oneka ghost project classifier.

Produces:
  satellite/models/ghost_detector_v1.pkl     — serialised sklearn Pipeline
  satellite/models/feature_importance.csv    — feature importances
  satellite/models/model_metrics.json        — CV scores for CI gates
  satellite/models/confusion_matrix.png      — CV confusion matrix (if matplotlib)
  satellite/models/roc_curve.png             — ROC curve (if matplotlib)
  satellite/docs/model_performance_report.md — human-readable report

Pipeline architecture:
  SimpleImputer(median) → StandardScaler → [SMOTE] → RandomForestClassifier
  SMOTE is applied only inside each CV training fold (via ImbLearn Pipeline).
  Falls back to class_weight='balanced' RF if imbalanced-learn is not installed.

Target metrics (5-fold stratified CV):
  AUC          ≥ 0.80
  Precision    ≥ 0.75  (ghost class)
  Recall       ≥ 0.70  (ghost class)
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from imblearn.over_sampling import SMOTE
    from imblearn.pipeline import Pipeline as ImbPipeline

    _HAS_IMBLEARN = True
except ImportError:
    _HAS_IMBLEARN = False
    warnings.warn(
        "imbalanced-learn not installed — training without SMOTE oversampling. "
        "Install with: uv pip install imbalanced-learn",
        stacklevel=2,
    )

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False


MODEL_VERSION = "v1"
MODEL_FILENAME = "ghost_detector_v1.pkl"
_CV_FOLDS = 5
_SMOTE_K_NEIGHBORS = 3  # reduced for small training sets (<20 minority samples)


# ── Pipeline factory ──────────────────────────────────────────────────────────


def _build_pipeline(random_state: int = 42) -> Pipeline:
    """
    Construct the classifier pipeline.

    With imbalanced-learn: Imputer → Scaler → SMOTE → RandomForest.
    Without imbalanced-learn: Imputer → Scaler → RandomForest(class_weight=balanced).
    """
    rf = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,
    )
    steps: list = [
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scaler", StandardScaler()),
    ]
    if _HAS_IMBLEARN:
        steps.append(("smote", SMOTE(random_state=random_state, k_neighbors=_SMOTE_K_NEIGHBORS)))
        return ImbPipeline(steps + [("classifier", rf)])

    return Pipeline(steps + [("classifier", rf)])


# ── Main entry point ──────────────────────────────────────────────────────────


def train_ghost_project_classifier(
    features_df: pd.DataFrame,
    labels: pd.Series,
    output_dir: Path,
    random_state: int = 42,
) -> tuple[Pipeline, dict]:
    """
    Train the ghost project classifier and persist all artefacts.

    Args:
        features_df: Feature matrix, shape (n_projects, 10).
        labels:      Binary Series — 1 = ghost, 0 = success.
        output_dir:  Directory to write model and artefacts (created if absent).
        random_state: RNG seed for reproducibility.

    Returns:
        Tuple of (fitted Pipeline, metrics dict).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    n_ghost = int(labels.sum())
    n_success = int((labels == 0).sum())
    n_total = len(labels)

    print(
        f"Training ghost project classifier  "
        f"({n_total} projects: {n_ghost} ghost / {n_success} success)"
    )
    if _HAS_IMBLEARN:
        print(f"  SMOTE oversampling: ON  (k_neighbors={_SMOTE_K_NEIGHBORS})")
    else:
        print("  SMOTE oversampling: OFF  (imbalanced-learn not installed)")

    pipeline = _build_pipeline(random_state)
    cv = StratifiedKFold(n_splits=_CV_FOLDS, shuffle=True, random_state=random_state)

    # ── 5-fold cross-validation ────────────────────────────────────────────────
    cv_results = cross_validate(
        pipeline,
        features_df,
        labels,
        cv=cv,
        scoring=["roc_auc", "precision", "recall", "f1"],
        return_train_score=False,
        error_score="raise",
    )

    mean_auc = float(np.mean(cv_results["test_roc_auc"]))
    mean_precision = float(np.mean(cv_results["test_precision"]))
    mean_recall = float(np.mean(cv_results["test_recall"]))
    mean_f1 = float(np.mean(cv_results["test_f1"]))

    metrics: dict = {
        "model_version": MODEL_VERSION,
        "n_samples": n_total,
        "n_ghost": n_ghost,
        "n_success": n_success,
        "cv_folds": _CV_FOLDS,
        "smote_applied": _HAS_IMBLEARN,
        "cv_auc": round(mean_auc, 4),
        "cv_precision_ghost": round(mean_precision, 4),
        "cv_recall_ghost": round(mean_recall, 4),
        "cv_f1_ghost": round(mean_f1, 4),
        "target_auc_met": mean_auc >= 0.80,
        "target_precision_met": mean_precision >= 0.75,
        "target_recall_met": mean_recall >= 0.70,
    }

    _print_cv_summary(metrics)

    # ── Refit on full dataset ──────────────────────────────────────────────────
    pipeline.fit(features_df, labels)

    # ── Feature importances ────────────────────────────────────────────────────
    rf_step = pipeline.named_steps["classifier"]
    importance_df = pd.DataFrame(
        {
            "feature": features_df.columns.tolist(),
            "importance": rf_step.feature_importances_,
        }
    ).sort_values("importance", ascending=False)

    importance_csv = output_dir / "feature_importance.csv"
    importance_df.to_csv(importance_csv, index=False)
    print(f"Feature importances  → {importance_csv}")

    # ── CV predictions for confusion matrix + ROC ──────────────────────────────
    y_proba_cv = cross_val_predict(
        _build_pipeline(random_state),
        features_df,
        labels,
        cv=cv,
        method="predict_proba",
    )[:, 1]
    y_pred_cv = (y_proba_cv >= 0.5).astype(int)

    print("\nClassification Report (CV predictions):")
    print(classification_report(labels, y_pred_cv, target_names=["success", "ghost"]))

    if _HAS_MPL:
        _save_confusion_matrix(labels, y_pred_cv, output_dir)
        _save_roc_curve(labels, y_proba_cv, mean_auc, output_dir)

    # ── Persist artefacts ──────────────────────────────────────────────────────
    model_path = output_dir / MODEL_FILENAME
    joblib.dump(pipeline, model_path)
    print(f"Model               → {model_path}")

    metrics_json = output_dir / "model_metrics.json"
    with open(metrics_json, "w") as fh:
        json.dump(metrics, fh, indent=2)
    print(f"Metrics JSON        → {metrics_json}")

    _write_performance_report(metrics, importance_df, output_dir)

    return pipeline, metrics


# ── Internal helpers ──────────────────────────────────────────────────────────


def _print_cv_summary(metrics: dict) -> None:
    print(f"\n{'─' * 55}")
    print(f"  Cross-Validation Results ({metrics['cv_folds']}-fold Stratified):")
    print(f"{'─' * 55}")

    def _row(label: str, val: float, target: float) -> str:
        met = "✓" if val >= target else "✗"
        return f"  {label:<28} {val:.4f}   (target ≥ {target:.2f})  {met}"

    print(_row("AUC (ROC)", metrics["cv_auc"], 0.80))
    print(_row("Precision (ghost class)", metrics["cv_precision_ghost"], 0.75))
    print(_row("Recall    (ghost class)", metrics["cv_recall_ghost"], 0.70))
    print(f"  {'F1 (ghost class)':<28} {metrics['cv_f1_ghost']:.4f}")
    print(f"{'─' * 55}\n")


def _save_confusion_matrix(y_true, y_pred, output_dir: Path) -> None:
    from sklearn.metrics import ConfusionMatrixDisplay

    fig, ax = plt.subplots(figsize=(5, 4))
    ConfusionMatrixDisplay.from_predictions(
        y_true, y_pred, display_labels=["success", "ghost"], ax=ax
    )
    ax.set_title("Ghost Project Classifier — Confusion Matrix (5-fold CV)")
    fig.tight_layout()
    path = output_dir / "confusion_matrix.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    print(f"Confusion matrix    → {path}")


def _save_roc_curve(y_true, y_score, auc: float, output_dir: Path) -> None:
    from sklearn.metrics import RocCurveDisplay

    fig, ax = plt.subplots(figsize=(5, 4))
    RocCurveDisplay.from_predictions(y_true, y_score, ax=ax)
    ax.set_title(f"ROC Curve — AUC = {auc:.4f} (5-fold CV)")
    fig.tight_layout()
    path = output_dir / "roc_curve.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    print(f"ROC curve           → {path}")


def _write_performance_report(
    metrics: dict,
    importance_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    docs_dir = output_dir.parent / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    report_path = docs_dir / "model_performance_report.md"

    overall_status = (
        "PASS"
        if (
            metrics["target_auc_met"]
            and metrics["target_precision_met"]
            and metrics["target_recall_met"]
        )
        else "PARTIAL" if metrics["target_auc_met"] else "FAIL"
    )

    def _tick(met: bool) -> str:
        return "Yes ✓" if met else "No ✗"

    try:
        importance_table = importance_df.to_markdown(index=False, floatfmt=".4f")
    except Exception:
        importance_table = importance_df.to_string(index=False)

    content = f"""# Ghost Project Classifier — Performance Report

**Model version:** `{metrics["model_version"]}`
**Training samples:** {metrics["n_samples"]} ({metrics["n_ghost"]} ghost, {metrics["n_success"]} success)
**CV strategy:** {metrics["cv_folds"]}-fold StratifiedKFold
**SMOTE applied:** {"Yes" if metrics["smote_applied"] else "No (imbalanced-learn not installed)"}
**Overall status:** **{overall_status}**

---

## Cross-Validation Metrics

| Metric | Score | Target | Met? |
|---|---|---|---|
| AUC (ROC) | {metrics["cv_auc"]:.4f} | ≥ 0.80 | {_tick(metrics["target_auc_met"])} |
| Precision (ghost) | {metrics["cv_precision_ghost"]:.4f} | ≥ 0.75 | {_tick(metrics["target_precision_met"])} |
| Recall (ghost) | {metrics["cv_recall_ghost"]:.4f} | ≥ 0.70 | {_tick(metrics["target_recall_met"])} |
| F1 (ghost) | {metrics["cv_f1_ghost"]:.4f} | — | — |

---

## Feature Importances

{importance_table}

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
"""
    report_path.write_text(content)
    print(f"Performance report  → {report_path}")
