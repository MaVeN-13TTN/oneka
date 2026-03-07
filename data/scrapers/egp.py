import asyncio
from typing import TYPE_CHECKING

from playwright.async_api import async_playwright
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from .base import BaseScraper, logger
from ..db import AsyncSessionLocal
from ..models import procurement_records, geolocation_records

if TYPE_CHECKING:
    from ..context import ProjectContext

# GPS quality tier scores (Tier 1 — highest confidence source)
EGP_MANUAL_PIN = 90
EGP_AUTO_GEOCODED = 70


class EGPScraper(BaseScraper):
    BASE_URL = "https://egpkenya.go.ke"
    TENDERS_URL = "https://egpkenya.go.ke/tender"
    API_URL_PART = "/api/xcommon/get-ten-tab-tender-details"

    async def fetch(self, ctx: "ProjectContext | None" = None) -> list[dict]:
        """
        Fetches tender data from e-GP Kenya.

        When *ctx* is None (bulk mode) navigates as before — Closed Works tenders,
        all results. When *ctx* is provided (targeted mode) searches for each term
        in ctx.search_terms and filters by ctx.procuring_entity if known.
        """
        if ctx is None:
            return await self._fetch_all()
        return await self._fetch_targeted(ctx)

    async def _fetch_all(self) -> list[dict]:
        """
        Legacy bulk mode — intercepts all closed Works tenders.
        Launches a headless browser, navigates to closed Works tenders,
        and intercepts the API response containing tender details.
        """
        data = []

        async with async_playwright() as p:
            logger.info("Launching browser...")
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
            )
            page = await context.new_page()

            async def handle_response(response):
                if self.API_URL_PART in response.url and response.status == 200:
                    try:
                        logger.info(f"Intercepted response from {response.url}")
                        json_data = await response.json()
                        if isinstance(json_data, dict):
                            if "respData" in json_data:
                                resp_data = json_data["respData"]
                                if isinstance(resp_data, dict) and "tenderDetails" in resp_data:
                                    data.extend(resp_data["tenderDetails"])
                                elif isinstance(resp_data, list):
                                    data.extend(resp_data)
                            elif "data" in json_data:
                                data.extend(json_data["data"])
                            else:
                                logger.warning(f"Unexpected keys: {list(json_data.keys())}")
                        elif isinstance(json_data, list):
                            data.extend(json_data)
                        logger.info(f"Collected {len(data)} items so far.")
                    except Exception as e:
                        logger.error(f"Failed to parse JSON from {response.url}: {e}")

            page.on("response", handle_response)

            logger.info(f"Navigating to {self.TENDERS_URL}...")
            await page.goto(self.TENDERS_URL, timeout=60000)

            try:
                await page.wait_for_load_state("networkidle")

                logger.info("Switching to 'Closed' tab...")
                await page.get_by_text("Closed", exact=True).click()
                await page.wait_for_timeout(3000)

                count = await page.locator("select[aria-label='Column Type']").count()
                if count > 0:
                    logger.info("Setting Procurement Category to 'Works'...")
                    await page.locator("select[aria-label='Column Type']").select_option("2")
                    await page.locator("button.btn-brown").first.click()
                else:
                    logger.info("Filter not visible, trying search toggle...")
                    search_btn = page.locator("button:has-text('Search')")
                    if await search_btn.count() > 0:
                        await search_btn.click()
                        await page.wait_for_timeout(1000)
                        await page.locator("select[aria-label='Column Type']").select_option("2")
                        await page.locator("button.btn-brown").first.click()

                logger.info("Waiting for data...")
                await page.wait_for_timeout(5000)

            except Exception as e:
                logger.error(f"Interaction failed: {e}")
                await page.screenshot(path="egp_error.png")

            await browser.close()

        return data

    async def _fetch_targeted(self, ctx: "ProjectContext") -> list[dict]:
        """
        Targeted mode — for each term in ctx.search_terms, fills the e-GP
        search box and collects intercepted API results. De-duplicates across
        terms by tender_no; optionally filters by ctx.procuring_entity.
        """
        collected: list[dict] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            browser_ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
            )
            page = await browser_ctx.new_page()

            async def handle_response(response):
                if self.API_URL_PART in response.url and response.status == 200:
                    try:
                        json_data = await response.json()
                        if isinstance(json_data, dict):
                            if "respData" in json_data:
                                resp_data = json_data["respData"]
                                if isinstance(resp_data, dict) and "tenderDetails" in resp_data:
                                    collected.extend(resp_data["tenderDetails"])
                                elif isinstance(resp_data, list):
                                    collected.extend(resp_data)
                            elif "data" in json_data:
                                collected.extend(json_data["data"])
                        elif isinstance(json_data, list):
                            collected.extend(json_data)
                    except Exception as e:
                        logger.error(f"EGP: failed to parse JSON from {response.url}: {e}")

            page.on("response", handle_response)

            for term in ctx.search_terms:
                logger.info(f"EGP targeted search: {term!r}")
                try:
                    await page.goto(self.TENDERS_URL, timeout=60000)
                    await page.wait_for_load_state("networkidle")

                    # Try to fill a text search input on the tender listing page
                    search_locator = page.locator(
                        'input[name="search"], input[type="search"], '
                        'input[placeholder*="search" i], input[aria-label*="search" i]'
                    )
                    if await search_locator.count() > 0:
                        await search_locator.first.fill(term)
                        await page.keyboard.press("Enter")
                    else:
                        # Fallback: category-only filter (same as bulk mode)
                        logger.warning(
                            f"EGP: search input not found for {term!r}, "
                            "falling back to Works Category filter."
                        )
                        count = await page.locator("select[aria-label='Column Type']").count()
                        if count > 0:
                            await page.locator("select[aria-label='Column Type']").select_option("2")
                            await page.locator("button.btn-brown").first.click()

                    await page.wait_for_timeout(5000)

                except Exception as e:
                    logger.error(f"EGP targeted search failed for {term!r}: {e}")
                    try:
                        await page.screenshot(path=f"egp_targeted_error_{term[:20]}.png")
                    except Exception:
                        pass

            await browser.close()

        # De-duplicate by tender_no; optionally filter by procuring_entity
        all_data: dict[str, dict] = {}
        for item in collected:
            tender_no = item.get("tenderrefno") or item.get("tender_no")
            if not tender_no:
                continue
            if ctx.procuring_entity:
                from rapidfuzz import fuzz
                pe = item.get("procuringEntity") or item.get("procuring_entity") or ""
                if fuzz.token_set_ratio(pe, ctx.procuring_entity) < 70:
                    continue
            all_data[tender_no] = item

        logger.info(
            f"EGP targeted: {len(all_data)} unique tenders "
            f"from {len(ctx.search_terms)} search term(s)"
        )
        return list(all_data.values())

    async def save(self, tenders_data):
        """
        Upserts tender data into procurement_records.
        Extracts GPS coordinates from deliveryLocation into geolocation_records
        when present (Tier 1 — highest quality geolocation).
        The PostGIS geom column is left NULL and populated by the
        backend geolocation service (Phase 2) which has geoalchemy2.
        """
        async with AsyncSessionLocal() as session:
            count = 0
            for item in tenders_data:
                tender_no = item.get("tenderrefno") or item.get("tender_no")
                if not tender_no:
                    continue

                # ── upsert procurement record ─────────────────────────────
                stmt = (
                    insert(procurement_records)
                    .values(
                        tender_number=tender_no,
                        tender_title=item.get("tendertitle"),
                        procuring_entity=item.get("procuringEntity"),
                        source_system="eGP",
                        extraction_method="playwright_intercept",
                    )
                    .on_conflict_do_nothing(index_elements=["tender_number"])
                )
                result = await session.execute(stmt)
                count += result.rowcount

                # ── extract GPS (Tier 1) — only for new records ───────────
                if result.rowcount == 0:
                    continue

                delivery = item.get("deliveryLocation") or {}
                geometry = delivery.get("geometry") or {}
                coords = geometry.get("coordinates")  # GeoJSON: [lon, lat]

                if coords and len(coords) >= 2:
                    lon, lat = float(coords[0]), float(coords[1])
                    quality = (
                        EGP_MANUAL_PIN
                        if delivery.get("locationType") == "MANUAL"
                        else EGP_AUTO_GEOCODED
                    )
                    geo_stmt = insert(geolocation_records).values(
                        source_system="eGP",
                        latitude=lat,
                        longitude=lon,
                        match_method="egp_embedded_gps",
                        match_score=quality,
                        match_confidence=quality,
                        facility_name=delivery.get("locationName"),
                        address=delivery.get("locationAddress"),
                    ).on_conflict_do_nothing()
                    await session.execute(geo_stmt)
                    logger.info(
                        f"GPS extracted for {tender_no}: "
                        f"lat={lat}, lon={lon}, quality={quality}"
                    )

            await session.commit()
            return count


if __name__ == "__main__":
    scraper = EGPScraper()
    asyncio.run(scraper.run())
