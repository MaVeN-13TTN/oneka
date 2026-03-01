import asyncio
import json
from playwright.async_api import async_playwright
from sqlalchemy import select
from backend.db import AsyncSessionLocal
from backend.models.tenders import Tender
from backend.scrapers.base import BaseScraper, logger

class EGPScraper(BaseScraper):
    BASE_URL = "https://egpkenya.go.ke"
    TENDERS_URL = "https://egpkenya.go.ke/tender"
    API_URL_PART = "/api/xcommon/get-ten-tab-tender-details"

    async def fetch(self):
        """
        Launches a headless browser, navigates to the closed works tenders,
        and intercepts the API response containing the data.
        """
        data = []
        
        async with async_playwright() as p:
            logger.info("Launching browser...")
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = await context.new_page()

            # Event handler for response interception
            async def handle_response(response):
                if self.API_URL_PART in response.url and response.status == 200:
                    try:
                        logger.info(f"Intercepted response from {response.url}")
                        json_data = await response.json()
                        # Inspect structure
                        if isinstance(json_data, dict):
                            # Found structure: {'status': ..., 'respData': ...}
                            if "respData" in json_data:
                                resp_data = json_data["respData"]
                                if isinstance(resp_data, dict) and "tenderDetails" in resp_data:
                                    data.extend(resp_data["tenderDetails"])
                                elif isinstance(resp_data, list):
                                    data.extend(resp_data)
                            elif "data" in json_data: # Keep fallback just in case
                                data.extend(json_data["data"])
                            else:
                                logger.warning(f"Unexpected JSON dict structure keys: {json_data.keys()}")
                        elif isinstance(json_data, list):
                            data.extend(json_data)
                        logger.info(f"Collected {len(data)} items so far.")
                    except Exception as e:
                        logger.error(f"Failed to parse JSON from {response.url}: {e}")

            page.on("response", handle_response)

            logger.info(f"Navigating to {self.TENDERS_URL}...")
            await page.goto(self.TENDERS_URL, timeout=60000)
            
            try:
                # Wait for initial load
                await page.wait_for_load_state("networkidle")
                
                # 1. Click 'Closed' tab
                logger.info("Switching to 'Closed' tab...")
                # Try specific text or fallback to class logic if needed
                await page.get_by_text("Closed", exact=True).click()
                await page.wait_for_timeout(3000)
                
                # 2. Open Filters (if needed - sometimes robust filter bars are visible)
                # Recon showed a "Search" button that expands filters?
                # Let's try to set the Procurement Category to 'Works' (Value 2)
                
                # The select might be hidden or require expanding a "Search" accordion
                # Try to interact with the select directly if visible
                count = await page.locator("select[aria-label='Column Type']").count()
                if count > 0:
                     logger.info("Setting Procurement Category to 'Works'...")
                     await page.locator("select[aria-label='Column Type']").select_option("2")
                     # Click Search button
                     await page.locator("button.btn-brown").first.click()
                else:
                    logger.info("Filter selector not found immediately. Trying to expand search...")
                    # Try finding a search toggle button
                    # Based on recon: clickable pixel was at X=459, Y=326.
                    # Let's look for a likely button text or icon
                    search_btn = page.locator("button:has-text('Search')")
                    if await search_btn.count() > 0:
                        await search_btn.click()
                        await page.wait_for_timeout(1000)
                        await page.locator("select[aria-label='Column Type']").select_option("2")
                        await page.locator("button.btn-brown").first.click()
                
                # Wait for data to reload
                logger.info("Waiting for data to load...")
                await page.wait_for_timeout(5000) 
                
            except Exception as e:
                logger.error(f"Interaction failed: {e}")
                # Take screenshot for debug
                await page.screenshot(path="egp_error.png")
            
            await browser.close()
            
        return data

    async def save(self, tenders_data):
        async with AsyncSessionLocal() as session:
            count = 0
            for item in tenders_data:
                # Debug keys
                if count == 0:
                     logger.debug(f"Sample item keys: {item.keys()}")

                tender_no = item.get("tenderrefno")
                if not tender_no: 
                    # Try 'tender_no' from PPIP mapping just in case
                    tender_no = item.get("tender_no")
                
                if not tender_no:
                    # Debug payload
                    # print(f"Skipping item without ref: {item.keys()}")
                    continue

                stmt = select(Tender).where(Tender.tender_no == tender_no)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing:
                    new_tender = Tender(
                        tender_no=tender_no,
                        description=item.get("tendertitle"),
                        # pe_name likely exists
                        procuring_entity=item.get("procuringEntity"), 
                        procurement_method=item.get("procurementMethod"),
                        procurement_category="Works",
                        raw_data=item
                    )
                    session.add(new_tender)
                    count += 1
            
            await session.commit()
            return count

if __name__ == "__main__":
    scraper = EGPScraper()
    asyncio.run(scraper.run())
