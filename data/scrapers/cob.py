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

        Returns a list of dicts:
            {"title": str, "url": str, "report_type": "annual" | "quarterly"}

        "annual" reports cover a full fiscal year (preferred for IntelligentCoBParser).
        "quarterly" reports are kept as fallback in case no annual report exists yet.
        """
        from playwright.async_api import async_playwright
        import re

        _QUARTERLY_MARKERS = (
            "quarter", "nine-months", "first-half", "second-half",
            "-q1-", "-q2-", "-q3-", "-q4-",
        )

        def _report_type(url: str) -> str:
            u = url.lower()
            if any(m in u for m in _QUARTERLY_MARKERS):
                return "quarterly"
            return "annual"

        report_links = []
        try:
            async with async_playwright() as p:
                print("Launching browser for CoB...")
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                print(f"Navigating to {self.REPORTS_URL}...")
                await page.goto(self.REPORTS_URL, timeout=120000, wait_until="domcontentloaded")

                links_data = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a.wpdm-download-link')).map(a => {
                        const titleParent = a.closest('.wpdm-link-template') || a.parentElement;
                        const text = titleParent ? titleParent.innerText.trim() : a.innerText.trim();
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

                    if item.get('onclick'):
                        match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", item['onclick'])
                        if match:
                            url = match.group(1)

                    if not url:
                        url = item.get('dataUrl') or (
                            item.get('href') if 'wpdmdl' in str(item.get('href')) else None
                        )

                    if url and ("fy-202" in url.lower() or "fy-201" in url.lower() or "fy-201" in url.lower()):
                        if text.lower() in ("download", ""):
                            slug = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
                            title = slug.replace('-', ' ').title()
                        else:
                            title = text

                        rtype = _report_type(url)
                        print(f"Found CoB Report [{rtype}]: {title} -> {url}")
                        report_links.append({"title": title, "url": url, "report_type": rtype})

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
        whose URL matches one of those fiscal years are downloaded (targeted
        mode).  For each matching fiscal year **every** available report is
        collected — both full annual reports and all quarterly breakdowns —
        to give IntelligentCoBParser the most complete financial picture
        spanning the project timeline from start_date to completion_date.

        FinancialService.ingest_cob_report_intelligent() parses each PDF using
        GPT-4o Vision and writes FinancialRecord rows.
        """
        reports = await self.find_reports()
        if not reports:
            logger.warning("CoBPoller: no report links found.")
            return

        if ctx and ctx.fiscal_years:
            # Build a candidate set for each target FY.
            # COB URLs encode the fiscal year as e.g. "fy-2023-24" (short form)
            # or "fy-2023-2024" (long form).  We check both.
            def _fy_variants(fy: str) -> list[str]:
                """Return URL fragments that identify a given FY string."""
                parts = fy.split("/")           # ["2023", "2024"]
                if len(parts) != 2:
                    return [fy.replace("/", "-")]
                y1, y2 = parts
                return [
                    f"fy-{y1}-{y2}",            # fy-2023-2024
                    f"fy-{y1}-{y2[2:]}",         # fy-2023-24
                ]

            selected: list[dict] = []
            for fy in ctx.fiscal_years:
                variants = _fy_variants(fy)
                matching = [
                    r for r in reports
                    if any(v in r["url"].lower() for v in variants)
                ]
                if not matching:
                    continue
                # Collect every available report for this FY:
                # annual + all quarterly breakdowns for maximum coverage
                selected.extend(matching)

            # De-duplicate by URL
            seen: set = set()
            deduped: list[dict] = []
            for r in selected:
                if r["url"] not in seen:
                    seen.add(r["url"])
                    deduped.append(r)

            reports = deduped
            logger.info(
                f"CoBPoller: filtered to {len(reports)} reports "
                f"for fiscal years {ctx.fiscal_years} "
                f"({sum(1 for r in reports if r.get('report_type')=='annual')} annual, "
                f"{sum(1 for r in reports if r.get('report_type')=='quarterly')} quarterly) "
                f"— all report types retained for full timeline coverage"
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
                        "report_type": rep.get("report_type", "unknown"),
                        "local_path": local_path,
                        "status": "downloaded",
                    }
                )
                logger.info(f"CoBPoller: downloaded [{rep.get('report_type','?')}] — {rep['title']}")

        CACHE_PATH.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(
            f"CoBPoller: cache updated — {len(existing)} reports at {CACHE_PATH}"
        )

if __name__ == "__main__":
    poller = CoBPoller()
    asyncio.run(poller.process())
