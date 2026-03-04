import asyncio
from datetime import datetime

import httpx
from sqlalchemy.dialects.postgresql import insert

from .base import BaseScraper, logger
from ..db import AsyncSessionLocal
from ..models import procurement_records


class PPIPScraper(BaseScraper):
    BASE_URL = "https://tenders.go.ke/api/active-tenders"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://tenders.go.ke/",
    }

    async def fetch(self):
        """Fetches active tenders from the PPIP internal JSON API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(self.BASE_URL, headers=self.HEADERS)
                response.raise_for_status()
                return response.json().get("data", [])
            except httpx.HTTPError as e:
                logger.error(f"Error fetching PPIP data: {e}")
                return []

    async def save(self, tenders_data):
        """
        Upserts tenders into procurement_records.
        PPIP is a one-time historical import (pre-2025 records).
        """
        async with AsyncSessionLocal() as session:
            count = 0
            for item in tenders_data:
                tender_no = item.get("tender_ref") or item.get("tender_no")
                if not tender_no:
                    continue

                award_dt = None
                raw_date = item.get("award_date") or item.get("date_awarded")
                if raw_date:
                    try:
                        award_dt = datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        pass

                stmt = (
                    insert(procurement_records)
                    .values(
                        tender_number=tender_no,
                        tender_title=item.get("title") or item.get("description"),
                        procuring_entity=str(item.get("pe_id", "")),
                        contract_sum_kes=item.get("amount") or item.get("contract_sum"),
                        award_date=award_dt,
                        source_system="PPIP",
                        extraction_method="api",
                    )
                    .on_conflict_do_nothing(index_elements=["tender_number"])
                )
                result = await session.execute(stmt)
                count += result.rowcount

            await session.commit()
            return count


if __name__ == "__main__":
    scraper = PPIPScraper()
    asyncio.run(scraper.run())
