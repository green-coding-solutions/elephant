"""Bundesnetzagentur (SMARD) provider for German grid carbon intensity."""

import logging
from datetime import datetime
from typing import List


from elephant.providers.bna_helper import get_co2intensity

from .base import CarbonIntensityProvider
from elephant.config import ProviderConfig


logger = logging.getLogger(__name__)

PROVICER_NAME = "bundesnetzagentur"

class BundesnetzagenturProvider(CarbonIntensityProvider):
    """Provider for Bundesnetzagentur (SMARD) carbon intensity data."""

    RESOLUTION = "quarterhour"

    def __init__(self, config: ProviderConfig):
        self.config = config

    def get_current(self, region: str) -> List[dict]:
        data = get_co2intensity(region, self.RESOLUTION, scan_all=False)

        if not data:
            return None

        returnList = []
        for i,j in data.items():
            returnList.append({
                "region": region,
                "time": i,
                "carbon_intensity": j,
                "provider": PROVICER_NAME,
                "resolution": self.RESOLUTION,
                "estimation": False,
            })

        return returnList

    def get_historical(self, region: str, start_time: datetime = None, end_time: datetime = None) -> List[dict]:
        """Return historical data, optionally filtered by time bounds."""

        data = self.get_current(region)
        if data is None:
            return None

        if start_time is None and end_time is None:
            return data

        filtered: List[dict] = []
        for entry in data:
            ts = entry.get("time", None)

            if end_time and ts < end_time:
                continue

            if end_time and ts > end_time:
                continue

            filtered.append(entry)

        return filtered
