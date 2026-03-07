"""
Perplexity Enrichment Service.

Transforms a raw project name (and optional user notes) into a fully
populated ProjectContext by querying the Perplexity sonar-pro API.

The service:
  1. Builds a structured JSON-extraction prompt around the project name
  2. Calls POST https://api.perplexity.ai/chat/completions
  3. Parses the JSON response into a ProjectContext
  4. Derives search_terms from canonical_name + aliases
  5. Returns the context (with warnings if confidence is low)

Raises:
  EnrichmentError — if the API is unreachable or returns an unparseable response.

Security:
  - API key is read from settings (env var PERPLEXITY_API_KEY), never logged.
  - Response content is parsed as JSON only — no eval or exec.
  - Source URLs from the response are stored as-is; they are never fetched.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from src.config import settings
from src.schemas.investigation import ProjectContext

logger = logging.getLogger(__name__)

# ── Low-confidence threshold ───────────────────────────────────────────────────
_LOW_CONFIDENCE_THRESHOLD = 0.6

# ── Prompt template ────────────────────────────────────────────────────────────
_QUERY_TEMPLATE = """\
You are a Kenya government infrastructure research analyst.
Find detailed information about the following government-funded \
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

Return JSON only. Do not include any explanation or markdown.
"""


class EnrichmentError(Exception):
    """Raised when Perplexity enrichment fails unrecoverably."""


class PerplexityEnrichmentService:
    """
    Enriches a raw project name into a ProjectContext using Perplexity AI.

    Usage::

        service = PerplexityEnrichmentService()
        ctx, warnings = service.enrich("Garissa County Headquarters")
    """

    _API_URL = "https://api.perplexity.ai/chat/completions"
    _TIMEOUT = 30  # seconds

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.perplexity_api_key
        self._model = model or settings.perplexity_model

    # ── Public interface ───────────────────────────────────────────────────────

    def enrich(
        self,
        project_name: str,
        user_notes: str | None = None,
    ) -> tuple[ProjectContext, list[str]]:
        """
        Query Perplexity and return a (ProjectContext, warnings) tuple.

        Args:
            project_name: Raw project name from the user.
            user_notes:   Optional extra context the user provided.

        Returns:
            Tuple of (ProjectContext, list[str]) where the list contains
            non-fatal warning messages (e.g., low confidence).

        Raises:
            EnrichmentError: If the API call fails or the response cannot
                             be parsed as valid JSON.
        """
        if not self._api_key:
            raise EnrichmentError(
                "PERPLEXITY_API_KEY is not set. "
                "Add it to .env or confirm it via PATCH /investigations/{id}/context."
            )

        prompt = _QUERY_TEMPLATE.format(
            project_name=project_name,
            user_notes=user_notes or "None provided",
        )

        raw = self._call_api(prompt)
        parsed = self._parse_response(raw)
        ctx = self._build_context(project_name, user_notes, parsed)
        warnings = self._collect_warnings(ctx)
        return ctx, warnings

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _call_api(self, prompt: str) -> dict[str, Any]:
        """
        POST to the Perplexity completions endpoint.

        Returns the raw parsed JSON dict from the API response.
        Raises EnrichmentError on network failures or non-200 responses.
        """
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "return_citations": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            with httpx.Client(timeout=self._TIMEOUT) as client:
                response = client.post(self._API_URL, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise EnrichmentError(
                f"Perplexity API is unreachable: {exc}"
            ) from exc

        if response.status_code != 200:
            raise EnrichmentError(
                f"Perplexity API returned HTTP {response.status_code}. "
                "Check PERPLEXITY_API_KEY and model name."
            )

        try:
            return response.json()
        except Exception as exc:
            raise EnrichmentError(
                f"Perplexity API response is not valid JSON: {exc}"
            ) from exc

    def _parse_response(self, api_response: dict[str, Any]) -> dict[str, Any]:
        """
        Extract the JSON payload from the chat completion response.

        The LLM content may be wrapped in markdown fences — we strip those
        before parsing.
        """
        try:
            content: str = api_response["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise EnrichmentError(
                f"Unexpected Perplexity response shape: {exc}"
            ) from exc

        # Strip optional ```json ... ``` fences
        content = re.sub(r"^```[a-z]*\n?", "", content.strip())
        content = re.sub(r"\n?```$", "", content.strip())

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise EnrichmentError(
                f"Perplexity content is not valid JSON: {exc}\nContent: {content[:200]}"
            ) from exc

    def _build_context(
        self,
        project_name: str,
        user_notes: str | None,
        parsed: dict[str, Any],
    ) -> ProjectContext:
        """Map the parsed Perplexity dict to a ProjectContext."""
        # Validate coordinates — must be [lat, lon] with plausible Kenya bounds
        raw_coords = parsed.get("coordinates")
        coordinates: tuple[float, float] | None = None
        if isinstance(raw_coords, (list, tuple)) and len(raw_coords) == 2:
            try:
                lat, lon = float(raw_coords[0]), float(raw_coords[1])
                # Kenya bounding box: lat -4.7 to 4.6, lon 33.9 to 41.9
                if -4.7 <= lat <= 4.6 and 33.9 <= lon <= 41.9:
                    coordinates = (lat, lon)
                else:
                    logger.warning(
                        "Perplexity returned coordinates outside Kenya bounds: "
                        "(%s, %s) — discarding", lat, lon
                    )
            except (TypeError, ValueError):
                pass

        # Ensure fiscal_years and aliases are lists of strings
        fiscal_years: list[str] = [
            str(y) for y in (parsed.get("fiscal_years") or [])
            if y is not None
        ]
        aliases: list[str] = [
            str(a) for a in (parsed.get("aliases") or [])
            if a is not None
        ]
        source_urls: list[str] = [
            str(u) for u in (parsed.get("source_urls") or [])
            if u is not None
        ]

        # Clamp confidence to [0, 1]
        raw_conf = parsed.get("confidence", 0.0)
        confidence = max(0.0, min(1.0, float(raw_conf or 0.0)))

        ctx = ProjectContext(
            project_name=project_name,
            user_notes=user_notes,
            canonical_name=parsed.get("canonical_name") or None,
            county=parsed.get("county") or None,
            constituency=parsed.get("constituency") or None,
            ward=parsed.get("ward") or None,
            coordinates=coordinates,
            project_type=parsed.get("project_type") or None,
            estimated_value_kes=parsed.get("estimated_value_kes") or None,
            contractor_name=parsed.get("contractor_name") or None,
            procuring_entity=parsed.get("procuring_entity") or None,
            award_date=parsed.get("award_date") or None,
            fiscal_years=fiscal_years,
            source_urls=source_urls,
            aliases=aliases,
            ministry=parsed.get("ministry") or None,
            vote_head=parsed.get("vote_head") or None,
            enrichment_confidence=confidence,
            enrichment_source="perplexity",
            enriched_at=datetime.now(timezone.utc),
        )

        # Derive search_terms from the enriched context
        ctx.search_terms = self._derive_search_terms(ctx)
        return ctx

    def _derive_search_terms(self, ctx: ProjectContext) -> list[str]:
        """
        Build the list of search strings to pass to each scraper.

        Combines canonical_name, aliases, and a county+type fragment so
        scrapers like NCA have targeted, high-signal search inputs.

        Example:
          canonical_name = "Construction of Bungoma District Hospital"
          aliases        = ["Bungoma District Hospital"]
          county         = "Bungoma"
          project_type   = "HEALTH"

          → ["Construction of Bungoma District Hospital",
             "Bungoma District Hospital",
             "Bungoma health"]
        """
        terms: list[str] = []

        if ctx.canonical_name:
            terms.append(ctx.canonical_name)

        for alias in ctx.aliases:
            if alias and alias not in terms:
                terms.append(alias)

        # Add a county + project-type keyword fragment as a fallback search
        if ctx.county and ctx.project_type:
            _TYPE_KEYWORDS = {
                "HEALTH": "health",
                "ROADS": "road",
                "EDUCATION": "school",
                "WATER": "water",
                "MARKETS": "market",
            }
            type_kw = _TYPE_KEYWORDS.get(ctx.project_type.upper())
            if type_kw:
                fragment = f"{ctx.county} {type_kw}"
                if fragment not in terms:
                    terms.append(fragment)

        return terms

    def _collect_warnings(self, ctx: ProjectContext) -> list[str]:
        """Return non-fatal warning messages about the enriched context."""
        warnings: list[str] = []

        if ctx.enrichment_confidence < _LOW_CONFIDENCE_THRESHOLD:
            warnings.append(
                f"Low enrichment confidence ({ctx.enrichment_confidence:.2f}). "
                "Review the context carefully before triggering scraping. "
                "You can correct fields via PATCH /investigations/{id}/context."
            )

        if not ctx.county:
            warnings.append(
                "County could not be determined from Perplexity results. "
                "Geolocation will rely on NER fallback (lower accuracy)."
            )

        if not ctx.aliases:
            warnings.append(
                "No aliases found. Scrapers will use canonical_name only — "
                "consider adding known alternative names manually."
            )

        if not ctx.fiscal_years:
            warnings.append(
                "No fiscal years found. CoBPoller will download all available "
                "BIRR reports instead of targeting specific years."
            )

        return warnings
