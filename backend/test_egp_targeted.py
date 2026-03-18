import asyncio
import sys
import os

# Add the parent directory to sys.path so we can import data and src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data.scrapers.egp import EGPScraper
from src.schemas.investigation import ProjectContext

async def main():
    scraper = EGPScraper()
    ctx = ProjectContext(project_name="Talanta Stadium", search_terms=["Talanta Stadium"])
    print("Running scraper fetch targeted...")
    results = await scraper._fetch_targeted(ctx)
    print(f"Results found: {len(results)}")
    if results:
        print(results[0])

if __name__ == "__main__":
    asyncio.run(main())
