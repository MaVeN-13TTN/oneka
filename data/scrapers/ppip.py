import httpx
import asyncio
import json
import os
from datetime import datetime
from backend.db import AsyncSessionLocal
from backend.models.tenders import Tender
from sqlalchemy.future import select
from backend.scrapers.base import BaseScraper, logger

class PPIPScraper(BaseScraper):
    BASE_URL = "https://tenders.go.ke/api/active-tenders"
    # Fallback/Headers to mimic browser if needed
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://tenders.go.ke/"
    }

    async def fetch(self):
        """
        Fetches active tenders from the PPIP internal API.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(self.BASE_URL, headers=self.HEADERS)
                response.raise_for_status()
                data = response.json()
                return data.get("data", [])
            except httpx.HTTPError as e:
                logger.error(f"Error fetching PPIP data: {e}")
                return []

    async def save(self, tenders_data):
        """
        Saves fetched tenders to the database, avoiding duplicates.
        """
        async with AsyncSessionLocal() as session:
            count = 0
            for item in tenders_data:
                # Adjust fields based on actual API response structure
                tender_no = item.get("tender_ref") or item.get("tender_no")
                
                if not tender_no:
                    continue

                # Check if exists
                stmt = select(Tender).where(Tender.tender_no == tender_no)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing:
                    # Parse dates if possible (ignoring for MVP simplicity, just storing if needed or handled by generic parser)
                    # For MVP let's leave dates as None or try basics if keys exist
                    
                    new_tender = Tender(
                        tender_no=tender_no,
                        description=item.get("title"),
                        procuring_entity=str(item.get("pe_id")), # pe_id is int in response, model expects string? Entity name not in this list, maybe in another endpoint or lookup. Storing ID for now.
                        procurement_method=str(item.get("procurement_method_id")),
                        procurement_category=str(item.get("procurement_category_id")),
                        # Date parsing would go here
                        raw_data=item
                    )
                    session.add(new_tender)
                    count += 1
            
            await session.commit()
            return count

if __name__ == "__main__":
    scraper = PPIPScraper()
    asyncio.run(scraper.run())
