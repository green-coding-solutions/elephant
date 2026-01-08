"""
Bundesnetzagentur (SMARD) provider for German grid carbon intensity.
This is quite the crazy provider that returns all data that the Bundesnetzagentur porovides.
This is 11 year old data with quarter hour resolution!!!!

Running this takes quite some time and is not recommended for production use.
"""

import logging
from datetime import datetime
from typing import List


from elephant.providers.bna_helper import get_co2intensity

from .base import CarbonIntensityProvider
from elephant.config import ProviderConfig


logger = logging.getLogger(__name__)

PROVIDER_NAME = "bundesnetzagentur"

class BundesnetzagenturProvider(CarbonIntensityProvider):
    """Provider for Bundesnetzagentur (SMARD) carbon intensity data."""

    RESOLUTION = "quarterhour"

    def __init__(self, config: ProviderConfig):
        self.config = config

    def get_current(self, region: str) -> List[dict]:
        data = get_co2intensity(region, self.RESOLUTION, scan_all=True)

        if not data:
            return None

        returnList = []
        for i,j in data.items():
            returnList.append({
                "region": region,
                "time": i,
                "carbon_intensity": j,
                "provider": PROVIDER_NAME,
                "resolution": self.RESOLUTION,
                "estimation": False,
            })

        return returnList

    def get_historical(self, region: str, start_time: datetime = None, end_time: datetime = None) -> List[dict]:
        raise NotImplementedError("Bundesnetzagentur all provider does not support historical data filtering as it takes too long to fetch all data.")

    def get_future(self, region: str) -> List[dict]:
        raise NotImplementedError("Bundesnetzagentur all provider does not support future data.")
