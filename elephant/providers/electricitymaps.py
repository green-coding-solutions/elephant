"""ElectricityMaps provider for carbon intensity data."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import requests
from fastapi import HTTPException
from requests import HTTPError, RequestException, Response

from elephant.config import ProviderConfig

from .base import CarbonIntensityProvider


logger = logging.getLogger(__name__)

BASE_URL = "https://api.electricitymaps.com"
PROVIDER_NAME = "electricitymaps"
RESOLUTION = "5_minutes"

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
            raise HTTPException(status_code=503, detail="ElectricityMaps service temporarily unavailable") from exc

    def get_current(self, region: str) -> List[dict]:
        """Get current carbon intensity for a region."""
        response = self._get("/v3/carbon-intensity/latest",
                              params={"zone": region, "temporalGranularity": RESOLUTION})
        data = response.json()
        item_time = datetime.fromisoformat(data["datetime"].replace("Z", "+00:00"))
        return [
            {
                "region": region,
                "time": item_time,
                "carbon_intensity": data["carbonIntensity"],
                "provider": PROVIDER_NAME,
                "resolution": RESOLUTION,
                "estimation": data.get("isEstimated", False),
            }
        ]

    def get_historical(self, region: str, start_time: datetime = None, end_time: datetime = None) -> List[dict]:
        """Get historical carbon intensity data for a region and time range."""
        if start_time is None:
            start_time = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        if end_time is None:
            end_time = datetime.now(tz=timezone.utc)

        response = self._get(
            "/v3/carbon-intensity/past-range",
            params={
                "zone": region,
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "temporalGranularity": RESOLUTION,
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
                    "resolution": RESOLUTION,
                    "estimation": item.get("isEstimated", False),
                }
            )
        return all_data

    def get_future(self, region: str) -> List[dict]:

        response = self._get(
            "/v3/carbon-intensity/forecast",
            params={
                "zone": region,
                "temporalGranularity": RESOLUTION,
            },
        )

        all_data = []
        for item in response.json().get("forecast", []):
            item_time = datetime.fromisoformat(item["datetime"].replace("Z", "+00:00"))
            all_data.append(
                {
                    "region": region,
                    "time": item_time,
                    "carbon_intensity": item["carbonIntensity"],
                    "provider": PROVIDER_NAME,
                    "resolution": RESOLUTION,
                    "estimation": True,
                }
            )

        return all_data
