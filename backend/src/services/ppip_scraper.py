"""
PPIP Web Scraper - Scrape tender data from Public Procurement Information Portal.

Implements transparent scraping with rate limiting and error handling as per
Sprint 2 requirements (5s intervals, transparent User-Agent).
"""

import requests
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Any
import time
import logging
from datetime import datetime
from urllib.parse import urljoin, urlparse
import re
from decimal import Decimal

from src.config import settings


# Configure logging
logger = logging.getLogger(__name__)


class PPIPScraper:
    """
    PPIP tender scraper with rate limiting and transparent identification.

    Features:
    - 5 second rate limiting between requests
    - Transparent User-Agent identification
    - Retry logic with exponential backoff
    - PDF download support
    - Error handling and logging
    """

    def __init__(self):
        self.base_url = settings.ppip_base_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "ONEKA AI Bot/1.0 (Infrastructure Auditing; dev@oneka.ai)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
            }
        )
        self.rate_limit_seconds = 5.0
        self.last_request_time: Optional[float] = None

        # Statistics
        self.stats = {
            "total_scraped": 0,
            "successful": 0,
            "failed": 0,
            "duplicates": 0,
            "errors": [],
        }

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests (5 seconds minimum)"""
        if self.last_request_time:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.rate_limit_seconds:
                sleep_time = self.rate_limit_seconds - elapsed
                logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)

        self.last_request_time = time.time()

    def _make_request(
        self, url: str, max_retries: int = 3, timeout: int = 30
    ) -> Optional[requests.Response]:
        """
        Make HTTP request with retry logic and error handling.

        Args:
            url: URL to fetch
            max_retries: Maximum number of retry attempts
            timeout: Request timeout in seconds

        Returns:
            Response object or None if all retries failed
        """
        for attempt in range(max_retries):
            try:
                self._rate_limit()

                logger.info(
                    f"Fetching URL: {url} (attempt {attempt + 1}/{max_retries})"
                )
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()

                return response

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1} for {url}")
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)  # Exponential backoff
                else:
                    logger.error(f"Max retries exceeded for {url}")
                    self.stats["errors"].append(f"Timeout: {url}")

            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error {e.response.status_code} for {url}")
                self.stats["errors"].append(f"HTTP {e.response.status_code}: {url}")
                return None

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed for {url}: {e}")
                self.stats["errors"].append(f"Request error: {url}")
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)

        return None

    def scrape_tenders_list(
        self, category: str = "all", max_pages: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Scrape list of tenders from PPIP.

        Args:
            category: Tender category filter (default: "all")
            max_pages: Maximum number of pages to scrape

        Returns:
            List of tender dictionaries with scraped data
        """
        tenders = []

        logger.info(
            f"Starting PPIP scrape for category '{category}', max {max_pages} pages"
        )

        for page_num in range(1, max_pages + 1):
            # Construct URL for tender listing page
            # Note: Actual PPIP URL structure would be determined during implementation
            list_url = f"{self.base_url}/tenders?category={category}&page={page_num}"

            response = self._make_request(list_url)
            if not response:
                logger.warning(f"Failed to fetch page {page_num}, stopping pagination")
                break

            # Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # Extract tenders from page
            page_tenders = self._extract_tenders_from_page(soup)

            if not page_tenders:
                logger.info(f"No tenders found on page {page_num}, stopping pagination")
                break

            tenders.extend(page_tenders)
            logger.info(f"Extracted {len(page_tenders)} tenders from page {page_num}")

            self.stats["total_scraped"] += len(page_tenders)

        logger.info(f"Scraping complete. Total tenders collected: {len(tenders)}")
        return tenders

    def _extract_tenders_from_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Extract tender data from a listing page.

        Args:
            soup: BeautifulSoup object of the page

        Returns:
            List of tender dictionaries
        """
        tenders = []

        # Note: Actual selectors would be determined by inspecting real PPIP HTML
        # This is a template structure
        tender_rows = soup.select("tr.tender-row, div.tender-item")

        for row in tender_rows:
            try:
                tender_data = self._extract_tender_data(row)
                if tender_data:
                    tenders.append(tender_data)
                    self.stats["successful"] += 1
            except Exception as e:
                logger.warning(f"Failed to extract tender data: {e}")
                self.stats["failed"] += 1

        return tenders

    def _extract_tender_data(self, element: Any) -> Optional[Dict[str, Any]]:
        """
        Extract tender data from a single HTML element.

        Args:
            element: BeautifulSoup element containing tender data

        Returns:
            Dictionary with tender data or None if extraction failed
        """
        try:
            # Extract tender number
            tender_number_elem = element.select_one(".tender-number, td.tender-ref")
            tender_number = (
                tender_number_elem.get_text(strip=True) if tender_number_elem else None
            )

            if not tender_number:
                return None

            # Extract tender title
            title_elem = element.select_one(".tender-title, td.tender-name")
            tender_title = title_elem.get_text(strip=True) if title_elem else None

            # Extract procuring entity
            entity_elem = element.select_one(".procuring-entity, td.entity")
            procuring_entity = entity_elem.get_text(strip=True) if entity_elem else None

            # Extract contract sum
            amount_elem = element.select_one(".contract-sum, td.amount")
            contract_sum = (
                self._parse_amount(amount_elem.get_text(strip=True))
                if amount_elem
                else None
            )

            # Extract dates
            award_date_elem = element.select_one(".award-date, td.date-award")
            award_date = (
                self._parse_date(award_date_elem.get_text(strip=True))
                if award_date_elem
                else None
            )

            # Extract contractor
            contractor_elem = element.select_one(".contractor, td.contractor-name")
            contractor_name = (
                contractor_elem.get_text(strip=True) if contractor_elem else None
            )

            # Extract PDF URL
            pdf_link = element.select_one('a[href*=".pdf"], a.download-link')
            document_url = (
                urljoin(self.base_url, pdf_link["href"])
                if pdf_link and pdf_link.get("href")
                else None
            )

            # Extract detail page URL
            detail_link = element.select_one("a.view-details, a.tender-link")
            detail_url = (
                urljoin(self.base_url, detail_link["href"])
                if detail_link and detail_link.get("href")
                else None
            )

            tender_data = {
                "source_system": "PPIP",
                "tender_number": tender_number,
                "tender_title": tender_title,
                "procuring_entity": procuring_entity,
                "contract_sum_kes": contract_sum,
                "award_date": award_date,
                "contractor_name": contractor_name,
                "document_url": document_url,
                "detail_url": detail_url,
                "extraction_method": "scraping",
                "data_quality": self._calculate_data_quality(
                    tender_title, procuring_entity, contractor_name
                ),
            }

            return tender_data

        except Exception as e:
            logger.error(f"Error extracting tender data: {e}")
            return None

    def scrape_tender_details(self, detail_url: str) -> Optional[Dict[str, Any]]:
        """
        Scrape detailed information from a tender's detail page.

        Args:
            detail_url: URL of tender detail page

        Returns:
            Dictionary with detailed tender information
        """
        response = self._make_request(detail_url)
        if not response:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract additional details from detail page
        details = {}

        try:
            # Expected completion date
            completion_elem = soup.select_one(".completion-date, #completion-date")
            if completion_elem:
                details["expected_completion_date"] = self._parse_date(
                    completion_elem.get_text(strip=True)
                )

            # Contract duration
            duration_elem = soup.select_one(".contract-duration, #duration")
            if duration_elem:
                details["contract_duration_months"] = self._parse_duration(
                    duration_elem.get_text(strip=True)
                )

            # Contractor PIN
            pin_elem = soup.select_one(".contractor-pin, #contractor-pin")
            if pin_elem:
                details["contractor_pin"] = pin_elem.get_text(strip=True)

            # NCA License
            nca_elem = soup.select_one(".nca-license, #nca-license")
            if nca_elem:
                details["contractor_nca_license"] = nca_elem.get_text(strip=True)

            return details

        except Exception as e:
            logger.error(f"Error extracting tender details: {e}")
            return {}

    def download_pdf(self, pdf_url: str, save_path: str) -> bool:
        """
        Download PDF document from URL.

        Args:
            pdf_url: URL of PDF document
            save_path: Local file path to save PDF

        Returns:
            True if download successful, False otherwise
        """
        try:
            response = self._make_request(pdf_url)
            if not response:
                return False

            # Verify content type
            content_type = response.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower():
                logger.warning(f"URL does not return PDF: {content_type}")
                return False

            # Write PDF to file
            with open(save_path, "wb") as f:
                f.write(response.content)

            logger.info(f"Downloaded PDF: {save_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to download PDF from {pdf_url}: {e}")
            return False

    @staticmethod
    @staticmethod
    def _parse_amount(amount_str: Optional[str]) -> Optional[Decimal]:
        """Parse monetary amount from string (e.g., 'KES 1,234,567.89')"""
        if not amount_str:
            return None

        # Remove currency symbols and commas
        clean_str = re.sub(r"[KES,\s]", "", amount_str)

        try:
            return Decimal(clean_str)
        except:
            return None

    @staticmethod
    def _parse_date(date_str: str) -> Optional[str]:
        """Parse date from string and return ISO format"""
        if not date_str:
            return None

        # Common date formats in Kenya
        date_patterns = [
            r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})",  # DD/MM/YYYY or DD-MM-YYYY
            r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})",  # YYYY/MM/DD or YYYY-MM-DD
        ]

        for pattern in date_patterns:
            match = re.search(pattern, date_str)
            if match:
                # Return as ISO format string
                # Actual parsing would use datetime for proper validation
                return match.group(0).replace("/", "-")

        return None

    @staticmethod
    def _parse_duration(duration_str: str) -> Optional[int]:
        """Parse contract duration in months from string"""
        if not duration_str:
            return None

        # Extract number from string like "12 months" or "1 year"
        match = re.search(r"(\d+)", duration_str)
        if match:
            duration = int(match.group(1))

            # Convert years to months if mentioned
            if "year" in duration_str.lower():
                duration *= 12

            return duration

        return None

    @staticmethod
    def _calculate_data_quality(
        tender_title: Optional[str],
        procuring_entity: Optional[str],
        contractor_name: Optional[str],
    ) -> int:
        """
        Calculate data quality score based on field completeness.

        Returns:
            Score from 0-100
        """
        fields = [tender_title, procuring_entity, contractor_name]
        filled_fields = sum(1 for f in fields if f and f.strip())

        # Base score on completeness
        base_score = (filled_fields / len(fields)) * 100

        return int(base_score)

    def get_stats(self) -> Dict[str, Any]:
        """Get scraping statistics"""
        return {
            "total_tenders_scraped": self.stats["total_scraped"],
            "successful_downloads": self.stats["successful"],
            "failed_downloads": self.stats["failed"],
            "duplicates_skipped": self.stats["duplicates"],
            "errors": self.stats["errors"][:10],  # Limit to first 10 errors
            "last_scrape_timestamp": datetime.utcnow().isoformat(),
        }

    def reset_stats(self) -> None:
        """Reset scraping statistics"""
        self.stats = {
            "total_scraped": 0,
            "successful": 0,
            "failed": 0,
            "duplicates": 0,
            "errors": [],
        }
