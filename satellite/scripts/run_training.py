"""
CLI wrapper for ghost project classifier training.

Usage (run from the satellite/ directory)::

    python scripts/run_training.py \\
        --data data/training/training_projects.csv \\
        --output models/

Or from the repo root::

    python satellite/scripts/run_training.py \\
        --data satellite/data/training/training_projects.csv \\
        --output satellite/models/

Exits 0 on success (even if AUC target is missed — model is still saved).
Exits 1 only on hard errors (file not found, import failure, etc.).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── Ensure satellite/src is importable regardless of working directory ─────────
_SCRIPT_DIR = Path(__file__).resolve().parent   # satellite/scripts/
_SAT_ROOT = _SCRIPT_DIR.parent                  # satellite/
_SAT_SRC = _SAT_ROOT / "src"

for _p in (_SAT_SRC, _SAT_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ── Import training modules ────────────────────────────────────────────────────
try:
    from feature_engineering import FeatureEngineer  # type: ignore[import]
    from train_model import train_ghost_project_classifier  # type: ignore[import]
except ImportError as exc:
    print(
        f"ERROR: Cannot import training modules — {exc}\n"
        "Make sure you have installed satellite/requirements.txt:\n"
        "  uv pip install scikit-learn joblib imbalanced-learn pandas",
        file=sys.stderr,
    )
    sys.exit(1)


def _resolve_path(raw: str, default_base: Path) -> Path:
    """Resolve relative paths against ``default_base``; return absolute paths as-is."""
    p = Path(raw)
    return p if p.is_absolute() else (default_base / p).resolve()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train the Oneka ghost project RandomForest classifier.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data",
        default="data/training/training_projects.csv",
        metavar="CSV_PATH",
        help="Path to labelled training CSV (default: data/training/training_projects.csv)",
    )
    parser.add_argument(
        "--output",
        default="models/",
        metavar="OUTPUT_DIR",
        help="Directory for model artefacts (default: models/)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        metavar="INT",
        help="Random seed for reproducibility (default: 42)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    data_path = _resolve_path(args.data, _SAT_ROOT)
    output_dir = _resolve_path(args.output, _SAT_ROOT)

    if not data_path.exists():
        print(
            f"ERROR: Training CSV not found: {data_path}\n"
            "Run from satellite/ with --data data/training/training_projects.csv",
            file=sys.stderr,
        )
        return 1

    print(f"Training data   : {data_path}")
    print(f"Output directory: {output_dir}")
    print(f"Random seed     : {args.seed}\n")

    fe = FeatureEngineer()
    X, y = fe.build_training_dataframe(data_path)
    print(f"Feature matrix  : {X.shape[0]} projects × {X.shape[1]} features")
    print(f"Label counts    : {y.value_counts().to_dict()}  (1=ghost, 0=success)\n")

    _, metrics = train_ghost_project_classifier(
        X, y, output_dir, random_state=args.seed
    )

    if metrics["target_auc_met"]:
        print(
            f"\nSUCCESS — AUC {metrics['cv_auc']:.4f} meets target ≥ 0.80  ✓"
        )
    else:
        print(
            f"\nWARNING — AUC {metrics['cv_auc']:.4f} is below target 0.80  ✗\n"
            "Model saved. Re-train once satellite_analyses table is populated\n"
            "with NDVI/SAR time-series to unlock full feature set.",
            file=sys.stderr,
        )

    return 0  # always exit 0 — model is written regardless of AUC target


if __name__ == "__main__":
    sys.exit(main())
