"""Tests for data/scrapers/base.py — BaseScraper orchestration."""

import asyncio

import pytest

from data.scrapers.base import BaseScraper


class FakeScraper(BaseScraper):
    """Concrete subclass for testing the abstract BaseScraper."""

    def __init__(self, fetch_return=None, save_return=0, fetch_error=None):
        super().__init__()
        self._fetch_return = fetch_return if fetch_return is not None else []
        self._save_return = save_return
        self._fetch_error = fetch_error

    async def fetch(self):
        if self._fetch_error:
            raise self._fetch_error
        return self._fetch_return

    async def save(self, data):
        return self._save_return


class TestBaseScraperRun:

    def test_run_returns_count_on_success(self):
        scraper = FakeScraper(fetch_return=[{"a": 1}, {"b": 2}], save_return=2)
        assert asyncio.run(scraper.run()) == 2

    def test_run_returns_zero_on_empty_fetch(self):
        scraper = FakeScraper(fetch_return=[], save_return=0)
        assert asyncio.run(scraper.run()) == 0

    def test_run_returns_zero_when_fetch_is_none(self):
        """BaseScraper.run() treats falsy fetch result as no data."""
        scraper = FakeScraper(fetch_return=None, save_return=5)
        assert asyncio.run(scraper.run()) == 0

    def test_run_returns_zero_on_fetch_exception(self):
        scraper = FakeScraper(fetch_error=RuntimeError("network down"))
        assert asyncio.run(scraper.run()) == 0

    def test_results_attribute_initialised(self):
        scraper = FakeScraper()
        assert scraper.results == []
