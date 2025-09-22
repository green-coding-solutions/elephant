"""Base provider interface for carbon intensity data."""

from abc import ABC, abstractmethod
from typing import List
from datetime import datetime

from ..models import CarbonIntensityResponse


class CarbonIntensityProvider(ABC):
    """Abstract base class for carbon intensity providers."""

    @abstractmethod
    async def get_current(self, location: str) -> CarbonIntensityResponse:
        """Get current carbon intensity for a location."""

    @abstractmethod
    async def get_historical(
        self, location: str, start_time: datetime, end_time: datetime
    ) -> List[CarbonIntensityResponse]:
        """Get historical carbon intensity data for a location and time range."""
