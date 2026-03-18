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
from datetime import date, datetime, timezone
from typing import Any

import httpx

from src.config import settings
from src.schemas.investigation import ProjectContext

logger = logging.getLogger(__name__)

# ── Low-confidence threshold ───────────────────────────────────────────────────
_LOW_CONFIDENCE_THRESHOLD = 0.6

_FY_RE = re.compile(r"^(\d{4})/(\d{4})$")


def _fy_from_date(date_str: str) -> str:
    """Return the Kenya fiscal year string (YYYY/YYYY) that contains `date_str`.

    Kenya FY runs July 1 – June 30:
      - Jan–Jun 2022  → FY 2021/2022
      - Jul–Dec 2022  → FY 2022/2023
    """
    year = int(date_str[:4])
    month = int(date_str[5:7]) if len(date_str) >= 7 else 7
    if month >= 7:
        return f"{year}/{year + 1}"
    return f"{year - 1}/{year}"


def _fiscal_years_range(start_str: str | None, end_str: str | None) -> list[str]:
    """Return every Kenya FY from start date to end date (inclusive).

    If end is None, runs to the current FY.
    """
    if not start_str:
        return []
    first_fy_year = int(_fy_from_date(start_str)[:4])

    if end_str:
        last_fy_year = int(_fy_from_date(end_str)[:4])
    else:
        today = date.today()
        last_fy_year = today.year if today.month >= 7 else today.year - 1

    if last_fy_year < first_fy_year:
        last_fy_year = first_fy_year

    return [f"{y}/{y + 1}" for y in range(first_fy_year, last_fy_year + 1)]


def _validate_fiscal_years(raw: list[str]) -> list[str]:
    """Keep only properly formatted FY strings (YYYY/YYYY, second = first + 1)."""
    valid = []
    for fy in raw:
        m = _FY_RE.match(str(fy))
        if m and int(m.group(2)) == int(m.group(1)) + 1:
            valid.append(fy)
    return valid

# ── Prompt template ────────────────────────────────────────────────────────────
_QUERY_TEMPLATE = """\
You are a Kenya government infrastructure research analyst with access to \
current news, official procurement portals, and government reports.

Research the following Kenya government-funded construction project and return \
precise factual information. Pay special attention to any official name changes \
(e.g. a project that was initially called X and later renamed to Y).

Project name: {project_name}
User notes: {user_notes}

Return a JSON object with EXACTLY the following fields (use null if genuinely unknown):
{{
  "canonical_name": "CURRENT official name — use the latest gazetted or \
officially announced name, even if different from the input name above",
  "historical_names": ["older name 1", "older name 2"],
  "county": "Kenya county name (single county, or primary county if multi-county)",
  "constituency": "constituency name or null",
  "ward": "ward name or null",
  "coordinates": [latitude, longitude] or null,
  "project_type": "one of HEALTH | ROADS | EDUCATION | WATER | MARKETS | STADIUMS | OTHER",
  "estimated_value_kes": number in KES or null,
  "contractor_name": "primary contractor name or null",
  "procuring_entity": "full name of government entity procuring this project",
  "ministry": "parent Ministry name as it appears in the COB BIRR budget vote (e.g. \
'Ministry of Sports, Culture and Heritage')",
  "vote_head": integer budget vote head number or null,
  "award_date": "YYYY-MM-DD or YYYY — date contract was awarded or null",
  "project_start_date": "YYYY-MM-DD or YYYY — when on-site construction began or null",
  "project_completion_date": "YYYY-MM-DD or YYYY — actual/expected completion \
date or null if still ongoing or unknown",
  "fiscal_years": ["YYYY/YYYY", ...] — ALL Kenya fiscal years (July–June) \
from project_start_date to project_completion_date (or current FY if ongoing). \
Each entry MUST be in format YYYY/YYYY where the second year equals first + 1, \
e.g. ["2021/2022", "2022/2023", "2023/2024"]. Leave [] only if start date is unknown,
  "source_urls": ["url1", "url2"],
  "confidence": float 0.0–1.0 reflecting how certain you are of the above facts
}}

IMPORTANT RULES:
- canonical_name must be the CURRENT official name (post any renaming)
- List ALL previous names under historical_names (they become scraper search aliases)
- fiscal_years: Kenya FY runs July 1 – June 30. A project starting in March 2022 \
begins in FY 2021/2022. A project starting August 2022 begins in FY 2022/2023. \
Include every FY from first to last year of activity.
- Return JSON only. No markdown, no explanations.
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
        # Validate coordinates — must be [lat, lon] within Kenya bounds
        raw_coords = parsed.get("coordinates")
        coordinates: tuple[float, float] | None = None
        if isinstance(raw_coords, (list, tuple)) and len(raw_coords) == 2:
            try:
                lat, lon = float(raw_coords[0]), float(raw_coords[1])
                if -4.7 <= lat <= 4.6 and 33.9 <= lon <= 41.9:
                    coordinates = (lat, lon)
                else:
                    logger.warning(
                        "Perplexity returned coordinates outside Kenya bounds: "
                        "(%s, %s) — discarding", lat, lon
                    )
            except (TypeError, ValueError):
                pass

        # Merge canonical aliases + historical_names into one aliases list
        aliases_raw: list[str] = [
            str(a) for a in (parsed.get("aliases") or []) if a is not None
        ]
        for hn in (parsed.get("historical_names") or []):
            if hn and str(hn) not in aliases_raw:
                aliases_raw.append(str(hn))
        # Always include the raw input project_name as an alias if it differs
        if project_name and project_name not in aliases_raw:
            # Only add if different from canonical
            canonical = parsed.get("canonical_name") or ""
            if project_name.lower() != canonical.lower():
                aliases_raw.append(project_name)

        source_urls: list[str] = [
            str(u) for u in (parsed.get("source_urls") or []) if u is not None
        ]

        # Dates
        start_date = parsed.get("project_start_date") or None
        completion_date = parsed.get("project_completion_date") or None

        # Fiscal years: validate what Perplexity gave us, fall back to date-derived range
        raw_fiscal = [str(y) for y in (parsed.get("fiscal_years") or []) if y is not None]
        fiscal_years = _validate_fiscal_years(raw_fiscal)
        if not fiscal_years and start_date:
            fiscal_years = _fiscal_years_range(start_date, completion_date)
            if fiscal_years:
                logger.info(
                    "Perplexity fiscal_years invalid/missing — derived %s from dates",
                    fiscal_years,
                )

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
            project_start_date=start_date,
            project_completion_date=completion_date,
            fiscal_years=fiscal_years,
            source_urls=source_urls,
            aliases=aliases_raw,
            ministry=parsed.get("ministry") or None,
            vote_head=parsed.get("vote_head") or None,
            enrichment_confidence=confidence,
            enrichment_source="perplexity",
            enriched_at=datetime.now(timezone.utc),
        )

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
