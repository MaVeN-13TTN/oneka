import asyncio
import re
from datetime import datetime
from typing import TYPE_CHECKING

from playwright.async_api import async_playwright
from sqlalchemy.dialects.postgresql import insert

from .base import BaseScraper, logger
from ..db import AsyncSessionLocal
from ..models import procurement_records

if TYPE_CHECKING:
    from ..context import ProjectContext

class NCAScraper(BaseScraper):
    BASE_URL = "https://www.nca.go.ke/approved-projects"
    
    # Heuristic list of search terms to uncover projects since there's no "View All"
    SEARCH_TERMS = [
        "Road", "Building", "Water", "School", "Hospital", 
        "Apartment", "Construction", "Proposed", "Academy",
        "Market", "Center", "Plaza", "Tower", "Highway"
    ]

    async def fetch(self, ctx: "ProjectContext | None" = None) -> list[dict]:
        """
        Fetches NCA approved projects.

        When *ctx* is None (bulk mode) loops over all SEARCH_TERMS.
        When *ctx* is provided (targeted mode) uses ctx.search_terms —
        typically 1–4 project-specific terms instead of the generic 14.
        """
        terms = (ctx.search_terms if ctx and ctx.search_terms else self.SEARCH_TERMS)
        all_rows = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            
            for term in terms:
                logger.info(f"Searching NCA for: {term}...")
                try:
                    await page.goto(self.BASE_URL, timeout=60000, wait_until="domcontentloaded")
                    # Wait for the search input to be in the DOM
                    await page.wait_for_selector('input[name="parameter"]', state="attached", timeout=30000)

                    logger.debug(f"Page Title: {await page.title()}")

                    # Fill the search input and submit via JS to avoid Playwright
                    # actionability-check timeouts on this site (element is not
                    # considered "visible" by Playwright but is fully interactive).
                    await page.evaluate(f"""() => {{
                        const inp = document.querySelector('input[name="parameter"]');
                        inp.value = {repr(term)};
                        inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                        inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                        // Submit the approved-projects form (second form on the page)
                        const form = Array.from(document.querySelectorAll('form'))
                            .find(f => f.action.includes('approved-projects'));
                        if (form) form.submit();
                    }}""")
                    logger.info(f"Submitted search for {term}...")
                    
                    # Wait for results (table to appear)
                    try:
                        # Wait for either result table OR "No Results" message to avoid long timeouts
                        # But prioritizing table.
                        await page.wait_for_selector('table tbody tr', state='attached', timeout=20000)
                    except Exception as e:
                        logger.warning(f"No results found for {term} (Timeout)")
                        # await page.screenshot(path=f"debug_nca_{term}.png")
                        continue

                    # Extract rows
                    # Table headers: ProjectID, ProjectName, DeveloperName, MainContractor, Architect, Engineer, ProjectType
                    rows = await page.evaluate("""() => {
                        const trs = Array.from(document.querySelectorAll('table tr'));
                        return trs.slice(1).map(tr => {
                            const tds = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
                            return tds;
                        });
                    }""")
                    
                    current_count = len(rows)
                    logger.info(f"Found {current_count} projects for term '{term}'")
                    all_rows.extend(rows)
                    
                except Exception as e:
                    logger.error(f"Error scraping term '{term}': {e}")
            
            await browser.close()
            # uniqueify based on project_id (index 0)
            unique_rows = {}
            for row in all_rows:
                if len(row) > 0:
                    unique_rows[row[0]] = row
            
            return list(unique_rows.values())

    async def save(self, rows):
        """
        Upserts NCA approved projects into procurement_records.
        NCA project_id is namespaced as 'NCA-<id>' to avoid clashes
        with tender numbers from other source systems.
        """
        async with AsyncSessionLocal() as session:
            count = 0
            for row in rows:
                if len(row) < 7:
                    continue

                # 0:ProjectID 1:Name 2:Developer 3:Contractor 4:Architect 5:Engineer 6:Type
                nca_id = f"NCA-{row[0]}"
                project_data = {
                    "tender_number": nca_id,
                    "tender_title": row[1],
                    "procuring_entity": row[2],  # developer acts as procuring entity
                    "contractor_name": row[3],
                    "source_system": "NCA",
                    "extraction_method": "playwright_scrape",
                }

                stmt = (
                    insert(procurement_records)
                    .values(project_data)
                    .on_conflict_do_update(
                        index_elements=["tender_number"],
                        set_=project_data,
                    )
                )

                try:
                    await session.execute(stmt)
                    count += 1
                except Exception as e:
                    logger.error(f"DB Error on {nca_id}: {e}")

            try:
                await session.commit()
            except Exception as e:
                logger.error(f"Commit Error: {e}")
                await session.rollback()
                return 0

            return count

if __name__ == "__main__":
    scraper = NCAScraper()
    asyncio.run(scraper.run())
