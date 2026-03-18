import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data.scrapers.ppip import PPIPScraper
from src.schemas.investigation import ProjectContext

async def main():
    scraper = PPIPScraper()
    ctx = ProjectContext(project_name="Talanta Stadium", search_terms=["Talanta Stadium"], aliases=["Talanta Sports City"])
    print("Running PPIP targeted scrape...")
    results = await scraper.fetch(ctx)
    print(f"Results found: {len(results)}")
    if results:
        print(results[0])

if __name__ == "__main__":
    asyncio.run(main())
