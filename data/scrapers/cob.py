import asyncio
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from .base import BaseScraper, logger

if TYPE_CHECKING:
    from ..context import ProjectContext

# Downloaded report metadata is tracked in a JSON cache file.
# FinancialService.ingest_cob_report() processes each PDF and writes
# rows to financial_records. A dedicated fiscal_reports DB table
# is planned for Phase 2 migration 003_add_fiscal_reports.py.
CACHE_PATH = Path(__file__).parent.parent / "cache" / "cob_reports.json"


class CoBPoller:
    REPORTS_URL = "https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/"
    DOWNLOAD_DIR = "data/raw/cob/"

    def __init__(self):
        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)

    async def find_reports(self):
        """
        Scrapes the reports page for PDF links using Playwright to handle JS redirects.
        """
        from playwright.async_api import async_playwright
        import re

        report_links = []
        try:
            async with async_playwright() as p:
                print("Launching browser for CoB...")
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                print(f"Navigating to {self.REPORTS_URL}...")
                # Increase timeout as CoB is slow
                await page.goto(self.REPORTS_URL, timeout=120000, wait_until="domcontentloaded")
                
                # Extract links via JS
                # Logic: Find .wpdm-download-link, get onclick/data-downloadurl, checks text in parent
                links_data = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a.wpdm-download-link')).map(a => {
                        const titleParent = a.closest('.wpdm-link-template') || a.parentElement;
                        const text = titleParent ? titleParent.innerText.trim() : a.innerText.trim();
                        // Get all attributes for debugging
                        const attrs = {};
                        for (let i = 0; i < a.attributes.length; i++) {
                            attrs[a.attributes[i].name] = a.attributes[i].value;
                        }
                        return {
                            text: text,
                            onclick: a.getAttribute('onclick'),
                            href: a.href,
                            dataUrl: a.getAttribute('data-downloadurl'),
                            outerHTML: a.outerHTML,
                            attributes: attrs
                        };
                    });
                }""")
                
                await browser.close()
                
                print(f"Found {len(links_data)} potential download links.")

                for item in links_data:
                    text = item['text']
                    url = None
                    
                    # Extract URL from onclick
                    if item.get('onclick'):
                        match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", item['onclick'])
                        if match:
                            url = match.group(1)
                    
                    # Fallback to data-downloadurl or href
                    if not url:
                        url = item.get('dataUrl') or (item.get('href') if 'wpdmdl' in str(item.get('href')) else None)

                    # Filter by URL keywords since text might just be "Download"
                    if url and ("fy-202" in url.lower() or "quarter" in url.lower() or "consolidated" in url.lower()):
                         # Derive title from URL if text is generic
                         if text.lower() == "download":
                             slug = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
                             # Clean up slug to make a readable title
                             title = slug.replace('-', ' ').title()
                         else:
                             title = text

                         print(f"Found CoB Report: {title} -> {url}")
                         report_links.append({"title": title, "url": url})
                         
                return report_links

        except Exception as e:
            print(f"Error scraping CoB: {e}")
            return []

    async def download_report(self, url, title):
        """
        Downloads a PDF file.
        """
        filename = url.split("/")[-1]
        local_path = os.path.join(self.DOWNLOAD_DIR, filename)
        
        if os.path.exists(local_path):
            print(f"File {filename} already exists.")
            return local_path

        async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
            try:
                print(f"Downloading {title}...")
                response = await client.get(url, follow_redirects=True)
                with open(local_path, "wb") as f:
                    f.write(response.content)
                print(f"Downloaded {filename}")
                return local_path
            except Exception as e:
                print(f"Failed to download {url}: {e}")
                return None

    async def process(self, ctx: "ProjectContext | None" = None) -> None:
        """
        Polls the COB website for BIRR report PDFs, downloads new ones,
        and persists their metadata to data/cache/cob_reports.json.

        When *ctx* is provided with *fiscal_years* populated, only reports
        matching those years are downloaded (targeted mode). The COB URL
        structure encodes the year as ``FY-YYYY-YYYY`` so matching is a simple
        substring check with ``/`` replaced by ``-``.

        FinancialService.ingest_cob_report() later parses each PDF and
        writes FinancialRecord rows to the database.
        """
        reports = await self.find_reports()
        if not reports:
            logger.warning("CoBPoller: no report links found.")
            return

        # Targeted mode: filter to relevant fiscal years only
        if ctx and ctx.fiscal_years:
            reports = [
                r for r in reports
                if any(fy.replace("/", "-") in r["url"] for fy in ctx.fiscal_years)
            ]
            logger.info(
                f"CoBPoller: filtered to {len(reports)} reports "
                f"for fiscal years {ctx.fiscal_years}"
            )

        # Load existing cache
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing: list = []
        if CACHE_PATH.exists():
            try:
                existing = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = []

        known_urls = {r["url"] for r in existing}

        for rep in reports:
            if rep["url"] in known_urls:
                logger.info(f"CoBPoller: already cached — {rep['title']}")
                continue

            local_path = await self.download_report(rep["url"], rep["title"])
            if local_path:
                existing.append(
                    {
                        "title": rep["title"],
                        "url": rep["url"],
                        "local_path": local_path,
                        "status": "downloaded",
                    }
                )
                logger.info(f"CoBPoller: downloaded — {rep['title']}")

        CACHE_PATH.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(
            f"CoBPoller: cache updated — {len(existing)} reports at {CACHE_PATH}"
        )

if __name__ == "__main__":
    poller = CoBPoller()
    asyncio.run(poller.process())
