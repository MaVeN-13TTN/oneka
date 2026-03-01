import asyncio
import json
from playwright.async_api import async_playwright
from backend.db import AsyncSessionLocal
from backend.models.core import Facility
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select
from backend.scrapers.base import BaseScraper, logger

class KMHFLScraper(BaseScraper):
    # Public API endpoint for KMHFL v3
    API_URL = "http://api.kmhfl.health.go.ke/api/facilities/facilities/"
    
    async def fetch(self):
        """
        Fetches all facilities using Playwright for network requests to handle potential 
        WAF/User-Agent issues better than bare requests.
        """
        data = []
        page_url = f"{self.API_URL}?page_size=1000&page=1" # Fetch large chunks
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            while page_url:
                logger.info(f"Fetching {page_url}...")
                try:
                    # Use APIRequestContext for pure API calls
                    api_request = context.request
                    response = await api_request.get(page_url)
                    
                    if response.status != 200:
                        logger.error(f"Error fetching {page_url}: {response.status} {response.status_text}")
                        break
                        
                    payload = await response.json()
                    
                    # Implementation detail: structure is usually { "results": [...], "next": "url", "count": N }
                    results = payload.get("results", [])
                    data.extend(results)
                    logger.info(f"Collected {len(results)} facilities. Total: {len(data)}")
                    
                    page_url = payload.get("next")
                    
                    # Safety break for development/testing
                    # if len(data) > 2000: break 
                    
                except Exception as e:
                    logger.error(f"Request failed: {e}")
                    break
            
            await browser.close()
            
        return data

    async def save(self, facilities):
        async with AsyncSessionLocal() as session:
            count = 0
            for fac in facilities:
                # Extract coordinates
                lat, long = None, None
                try:
                    lat_long = fac.get("lat_long")
                    if lat_long and len(lat_long) == 2:
                        lat, long = lat_long
                except:
                    pass
                
                # Extract details
                facility_data = {
                    "code": fac.get("code"),
                    "name": fac.get("name"),
                    "county": fac.get("county_name") or fac.get("county", {}).get("name"), # Handle nested obj
                    "sub_county": fac.get("sub_county_name") or fac.get("sub_county", {}).get("name"),
                    "ward": fac.get("ward_name") or fac.get("ward", {}).get("name"),
                    "keph_level": fac.get("keph_level_name") or fac.get("keph_level", {}).get("name"),
                    "operation_status": fac.get("operation_status_name") or fac.get("operation_status", {}).get("name"),
                    "owner": fac.get("owner_name") or fac.get("owner", {}).get("name"),
                    "beds": fac.get("number_of_beds", 0),
                    "cots": fac.get("number_of_cots", 0),
                    "lat": lat,
                    "long": long,
                    "source_url": self.API_URL
                }
                
                # Use standard insert with ON CONFLICT UPDATE
                stmt = insert(Facility).values(facility_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['code'],
                    set_=facility_data
                )
                
                try:
                    await session.execute(stmt)
                    count += 1
                except Exception as e:
                    logger.error(f"Error saving facility {fac.get('code')}: {e}")
            
            await session.commit()
            return count

if __name__ == "__main__":
    scraper = KMHFLScraper()
    asyncio.run(scraper.run())
