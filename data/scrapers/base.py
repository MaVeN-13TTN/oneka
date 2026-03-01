from abc import ABC, abstractmethod
import asyncio
from typing import Any, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    def __init__(self):
        self.results: List[Any] = []

    @abstractmethod
    async def fetch(self) -> List[Any]:
        """
        Fetches data from the source.
        Returns a list of raw data items.
        """
        pass

    @abstractmethod
    async def save(self, data: List[Any]) -> int:
        """
        Saves the fetched data to the database.
        Returns the count of saved items.
        """
        pass

    async def run(self) -> int:
        """
        Orchestrates the fetch and save operations.
        Returns the total number of items saved.
        """
        logger.info(f"Starting {self.__class__.__name__}...")
        try:
            data = await self.fetch()
            if not data:
                logger.warning(f"{self.__class__.__name__}: No data fetched.")
                return 0
            
            count = await self.save(data)
            logger.info(f"{self.__class__.__name__}: Finished. Saved {count} items.")
            return count
        except Exception as e:
            logger.error(f"{self.__class__.__name__} Failed: {e}", exc_info=True)
            return 0
