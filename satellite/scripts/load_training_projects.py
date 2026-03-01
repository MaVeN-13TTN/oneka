#!/usr/bin/env python3
"""
Load and visualize training projects for Sprint 1.

This script loads the training_projects.csv file and provides summary statistics
about the 30 historical infrastructure projects.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import matplotlib.pyplot as plt
from collections import Counter


def load_training_projects():
    """Load training projects from CSV."""
    csv_path = (
        Path(__file__).parent.parent / "data" / "training" / "training_projects.csv"
    )

    if not csv_path.exists():
        print(f"❌ Training projects CSV not found: {csv_path}")
        return None

    df = pd.read_csv(csv_path)
    print(f"✅ Loaded {len(df)} training projects")
    return df


def analyze_projects(df):
    """Analyze and display project statistics."""
    print("\n" + "=" * 70)
    print("TRAINING PROJECTS ANALYSIS")
    print("=" * 70)

    # Status distribution
    print("\n📊 Status Distribution:")
    status_counts = df["status"].value_counts()
    for status, count in status_counts.items():
        percentage = (count / len(df)) * 100
        print(f"  {status}: {count} projects ({percentage:.1f}%)")

    # County distribution
    print("\n🗺️  Geographic Distribution:")
    county_counts = df["county"].value_counts()
    print(f"  Total counties: {len(county_counts)}")
    print(f"  Projects per county: 1-{county_counts.max()}")

    # Budget statistics
    print("\n💰 Budget Statistics:")
    print(f"  Mean budget: KES {df['budget_kes'].mean():,.0f}")
    print(f"  Median budget: KES {df['budget_kes'].median():,.0f}")
    print(f"  Min budget: KES {df['budget_kes'].min():,.0f}")
    print(f"  Max budget: KES {df['budget_kes'].max():,.0f}")
    print(f"  Total: KES {df['budget_kes'].sum():,.0f}")

    # Project type distribution (inferred from name)
    print("\n🏗️  Project Types (inferred):")
    project_types = []
    for name in df["project_name"]:
        name_lower = name.lower()
        if (
            "hospital" in name_lower
            or "health" in name_lower
            or "clinic" in name_lower
            or "maternity" in name_lower
            or "icu" in name_lower
            or "lab" in name_lower
        ):
            project_types.append("Health")
        elif (
            "road" in name_lower or "bridge" in name_lower or "footbridge" in name_lower
        ):
            project_types.append("Roads")
        elif (
            "school" in name_lower
            or "polytechnic" in name_lower
            or "institute" in name_lower
            or "hostel" in name_lower
        ):
            project_types.append("Education")
        elif (
            "water" in name_lower
            or "dam" in name_lower
            or "irrigation" in name_lower
            or "sewerage" in name_lower
        ):
            project_types.append("Water")
        elif (
            "stadium" in name_lower
            or "market" in name_lower
            or "headquarters" in name_lower
            or "station" in name_lower
            or "pier" in name_lower
            or "airstrip" in name_lower
            or "airport" in name_lower
            or "assembly" in name_lower
            or "administration" in name_lower
        ):
            project_types.append("Infrastructure")
        else:
            project_types.append("Other")

    type_counts = Counter(project_types)
    for ptype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {ptype}: {count} projects")

    # Date range
    df["award_date"] = pd.to_datetime(df["award_date"])
    df["completion_date"] = pd.to_datetime(df["completion_date"])

    print("\n📅 Timeline:")
    print(
        f"  Award dates: {df['award_date'].min().strftime('%Y-%m-%d')} to {df['award_date'].max().strftime('%Y-%m-%d')}"
    )
    print(
        f"  Completion dates: {df['completion_date'].min().strftime('%Y-%m-%d')} to {df['completion_date'].max().strftime('%Y-%m-%d')}"
    )

    # Average project duration
    df["duration_months"] = (
        (df["completion_date"] - df["award_date"]).dt.days / 30
    ).round(1)
    print(f"  Average duration: {df['duration_months'].mean():.1f} months")
    print(f"  Median duration: {df['duration_months'].median():.1f} months")

    # Compare durations by status
    print("\n⏱️  Duration by Status:")
    for status in df["status"].unique():
        subset = df[df["status"] == status]
        print(f"  {status}: {subset['duration_months'].mean():.1f} months (avg)")

    return df


def display_sample_projects(df, n=5):
    """Display sample projects."""
    print("\n" + "=" * 70)
    print(f"SAMPLE PROJECTS (first {n})")
    print("=" * 70)

    for idx, row in df.head(n).iterrows():
        print(f"\n{row['project_id']}. {row['project_name']}")
        print(f"   County: {row['county']}")
        print(f"   Location: {row['latitude']:.4f}, {row['longitude']:.4f}")
        print(f"   Budget: KES {row['budget_kes']:,.0f}")
        print(f"   Status: {row['status'].upper()}")
        print(f"   Timeline: {row['award_date']} → {row['completion_date']}")
        print(f"   Evidence: {row['evidence_source']}")


def create_visualization(df):
    """Create simple visualization of projects."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "ONEKA AI - Training Projects Overview", fontsize=16, fontweight="bold"
    )

    # Status distribution
    ax1 = axes[0, 0]
    status_counts = df["status"].value_counts()
    colors = {"success": "#2ecc71", "ghost": "#e74c3c"}
    status_counts.plot(
        kind="bar",
        ax=ax1,
        color=[colors.get(x, "#95a5a6") for x in status_counts.index],
    )
    ax1.set_title("Project Status Distribution")
    ax1.set_xlabel("Status")
    ax1.set_ylabel("Number of Projects")
    ax1.set_xticklabels(ax1.get_xticklabels(), rotation=0)

    # Budget distribution
    ax2 = axes[0, 1]
    df.boxplot(column="budget_kes", by="status", ax=ax2)
    ax2.set_title("Budget Distribution by Status")
    ax2.set_xlabel("Status")
    ax2.set_ylabel("Budget (KES)")
    plt.sca(ax2)
    plt.xticks(rotation=0)

    # Geographic distribution (top counties)
    ax3 = axes[1, 0]
    county_counts = df["county"].value_counts().head(10)
    county_counts.plot(kind="barh", ax=ax3, color="#3498db")
    ax3.set_title("Top 10 Counties by Project Count")
    ax3.set_xlabel("Number of Projects")
    ax3.set_ylabel("County")

    # Duration distribution
    ax4 = axes[1, 1]
    df["duration_months"] = (
        pd.to_datetime(df["completion_date"]) - pd.to_datetime(df["award_date"])
    ).dt.days / 30
    df.boxplot(column="duration_months", by="status", ax=ax4)
    ax4.set_title("Project Duration by Status")
    ax4.set_xlabel("Status")
    ax4.set_ylabel("Duration (months)")
    plt.sca(ax4)
    plt.xticks(rotation=0)

    plt.tight_layout()

    # Save figure
    output_path = (
        Path(__file__).parent.parent
        / "data"
        / "training"
        / "training_projects_overview.png"
    )
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"\n📊 Visualization saved: {output_path}")

    return output_path


def main():
    """Main execution."""
    print("=" * 70)
    print("ONEKA AI - Training Projects Loader")
    print("=" * 70)

    # Load projects
    df = load_training_projects()
    if df is None:
        return 1

    # Analyze
    df = analyze_projects(df)

    # Display samples
    display_sample_projects(df, n=5)

    # Create visualization
    try:
        create_visualization(df)
    except Exception as e:
        print(f"\n⚠️  Visualization error: {e}")

    print("\n" + "=" * 70)
    print("✅ Training projects analysis complete")
    print("\nNext steps:")
    print("1. Set up Copernicus credentials in .env")
    print("2. Download satellite imagery for 5 test projects")
    print("3. Process NDVI and SAR data")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
