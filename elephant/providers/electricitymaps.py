"""ElectricityMaps provider for carbon intensity data."""

import logging
from datetime import datetime, timedelta
from typing import List, NoReturn

import requests
from fastapi import HTTPException
from requests import HTTPError, RequestException, Response

from elephant.config import ProviderConfig

from .base import CarbonIntensityProvider


logger = logging.getLogger(__name__)

BASE_URL = "https://api.electricitymaps.com"
PROVIDER_NAME = "electricitymaps"


class ElectricityMapsProvider(CarbonIntensityProvider):
    """Provider for ElectricityMaps carbon intensity data."""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.headers = {"auth-token": config.api_token} if config.api_token else {}

    def _get(self, path: str, params: dict) -> Response:
        """Perform a GET request with shared error handling."""
        try:
            response = requests.get(f"{BASE_URL}{path}", params=params, timeout=30.0, headers=self.headers)
            response.raise_for_status()
            return response

        except (HTTPError, RequestException) as exc:
            logger.error("ElectricityMaps request error: %s", exc)
            raise HTTPException(status_code=503, detail="ElectricityMaps service temporarily unavailable")

    def get_current(self, region: str) -> List[dict]:
        """Get current carbon intensity for a region."""
        response = self._get("/v3/carbon-intensity/latest", params={"zone": region})
        data = response.json()
        item_time = datetime.fromisoformat(data["datetime"].replace("Z", "+00:00"))
        return [
            {
                "region": region,
                "time": item_time,
                "carbon_intensity": data["carbonIntensity"],
                "provider": PROVIDER_NAME,
            }
        ]

    def get_historical(self, region: str, start_time: datetime = None, end_time: datetime = None) -> List[dict]:
        """Get historical carbon intensity data for a region and time range."""
        if start_time is None:
            start_time = datetime.now() - timedelta(hours=24)
        if end_time is None:
            end_time = datetime.now()

        response = self._get(
            "/v3/carbon-intensity/past-range",
            params={
                "zone": region,
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "temporalGranularity": "5_minutes",
            },
        )

        history_data = response.json().get("data", [])

        all_data = []
        for item in history_data:
            item_time = datetime.fromisoformat(item["datetime"].replace("Z", "+00:00"))
            all_data.append(
                {
                    "region": region,
                    "time": item_time,
                    "carbon_intensity": item["carbonIntensity"],
                    "provider": PROVIDER_NAME,
                }
            )

        return all_data