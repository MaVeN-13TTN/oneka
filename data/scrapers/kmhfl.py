import asyncio
import json
from pathlib import Path
from typing import Any, List

import httpx

from .base import BaseScraper, logger

# Local JSON cache — consumed by the geolocation service's Tier 2 fuzzy matcher.
# No Facility table exists yet; the DB migration is tracked in Phase 2.
CACHE_PATH = Path(__file__).parent.parent / "cache" / "kmhfl_facilities.json"


class KMHFLScraper(BaseScraper):
    # Correct endpoint — no /v2/ prefix (confirmed live: 500 is a server-side
    # AttributeError, not a 404; the path itself is correct).
    API_URL = "https://api.kmhfr.health.go.ke/api/facilities/facilities/"

    # Pagination: fetch in chunks of 100 (default page_size is 30).
    PAGE_SIZE = 100

    async def fetch(self) -> List[Any]:
        """
        Fetches all facilities from the KMHFL REST API using paginated GET requests.

        The /api/facilities/facilities/ endpoint currently returns HTTP 500
        (server-side AttributeError — a live production bug on the MoH server).
        When this happens the scraper logs a clear error and returns an empty list
        so the pipeline can continue; stale cache from a previous run is preserved.

        Returns:
            List of raw facility dicts, or [] if the server is unavailable.
        """
        data: List[Any] = []
        page_url = f"{self.API_URL}?format=json&page_size={self.PAGE_SIZE}&page=1"

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            while page_url:
                logger.info(f"Fetching {page_url}...")
                try:
                    response = await client.get(page_url)

                    if response.status_code == 500:
                        logger.error(
                            "KMHFL API returned HTTP 500 (server-side AttributeError — "
                            "live production bug on api.kmhfr.health.go.ke). "
                            "No data fetched. Stale cache at data/cache/kmhfl_facilities.json "
                            "will be preserved if it exists. "
                            "Report: https://servicedesk.health.go.ke/portal"
                        )
                        break

                    if response.status_code == 401 or response.status_code == 403:
                        logger.error(
                            f"KMHFL API returned HTTP {response.status_code}. "
                            "Authentication required — obtain OAuth2 credentials from "
                            "servicedesk.health.go.ke and set KMHFL_CLIENT_ID / "
                            "KMHFL_CLIENT_SECRET in .env."
                        )
                        break

                    if response.status_code != 200:
                        logger.error(
                            f"Unexpected response from KMHFL API: "
                            f"HTTP {response.status_code} — {response.text[:200]}"
                        )
                        break

                    payload = response.json()
                    results = payload.get("results", [])
                    data.extend(results)

                    total = payload.get("count", "?")
                    logger.info(
                        f"Collected {len(results)} facilities "
                        f"(total so far: {len(data)} / {total})"
                    )

                    page_url = payload.get("next")

                except httpx.RequestError as exc:
                    logger.error(f"Network error fetching KMHFL data: {exc}")
                    break

        return data

    async def save(self, facilities: List[Any]) -> int:
        """
        Saves scraped facilities to a local JSON cache file.

        The cache is consumed by the geolocation service's Tier 2 fuzzy matcher
        (spaCy NER + RapidFuzz). A dedicated kmhfl_facilities DB table will be
        added in Phase 2 via Alembic migration 003_add_kmhfl_facilities.py.

        Returns:
            Number of facilities written to cache.
        """
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(facilities, fh, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(facilities)} KMHFL facilities to {CACHE_PATH}")
        return len(facilities)


if __name__ == "__main__":
    scraper = KMHFLScraper()
    asyncio.run(scraper.run())
