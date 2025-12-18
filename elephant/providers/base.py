"""Base provider interface for carbon intensity data."""

from abc import ABC, abstractmethod
from typing import List
from datetime import datetime


class CarbonIntensityProvider(ABC):
    """Abstract base class for carbon intensity providers."""

    @abstractmethod
    def get_current(self, region: str) -> List[dict]:
        """Get current carbon intensity for a region."""

    @abstractmethod
    def get_historical(
        self, region: str, start_time: datetime, end_time: datetime) -> List[dict]:
        """Get historical carbon intensity data for a region and time range."""
