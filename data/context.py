"""
Lightweight ProjectContext dataclass for use within the data-acquisition layer.

This mirrors the fields consumed by targeted scrapers from the backend's
Pydantic ProjectContext schema, but without the fastapi/pydantic dependency
so the data/ layer remains independently importable.

The full schema with all enrichment fields lives in:
    backend/src/schemas/investigation.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProjectContext:
    """
    Enriched project context produced by PerplexityEnrichmentService.

    Only the fields consumed by the five targeted scrapers are included here.
    """

    canonical_name: Optional[str] = None
    search_terms: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    coordinates: Optional[tuple[float, float]] = None  # (lat, lon)
    fiscal_years: list[str] = field(default_factory=list)
    procuring_entity: Optional[str] = None
    # Additional fields used by IntelligentCoBParser (Stage 2 Vision extraction)
    ministry: Optional[str] = None
    county: Optional[str] = None
    vote_head: Optional[str] = None
