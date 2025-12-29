"""EnergyCharts provider for carbon intensity data."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import requests
from fastapi import HTTPException
from requests import HTTPError, RequestException

from elephant.config import ProviderConfig

from .base import CarbonIntensityProvider


logger = logging.getLogger(__name__)

BASE_URL = "https://api.energy-charts.info"
PROVIDER_NAME = "energycharts"
RESOLUTION="15_minutes"

class EnergyChartsProvider(CarbonIntensityProvider):
    """Provider for EnergyCharts carbon intensity data."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    def _get(self, region: str) -> dict:
        """Perform a GET request with shared error handling."""
        try:
            response = requests.get(f"{BASE_URL}/co2eq", params={"country": region.lower()}, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except (HTTPError, RequestException) as exc:
            logger.error("EnergyCharts request error: %s", exc)
            raise HTTPException(status_code=503, detail="EnergyCharts service temporarily unavailable") from exc

    def _build_entries(self, data: dict, region: str) -> List[dict]:
        """Merge measured and forecast data into a unified timeline."""
        timestamps = data.get("unix_seconds", [])
        co2eq = data.get("co2eq", [])
        co2eq_forecast = data.get("co2eq_forecast", [])

        entries: List[dict] = []
        for idx, ts in enumerate(timestamps):
            value = None

            if idx < len(co2eq) and co2eq[idx] is not None:
                value = co2eq[idx]
            elif idx < len(co2eq_forecast) and co2eq_forecast[idx] is not None:
                value = co2eq_forecast[idx]

            if value is None:
                continue

            entries.append(
                {
                    "region": region,
                    "time": datetime.fromtimestamp(ts, tz=timezone.utc),
                    "carbon_intensity": value,
                    "provider": PROVIDER_NAME,
                    "resolution": RESOLUTION,
                }
            )

        return entries

    def get_current(self, region: str) -> List[dict]:
        """Get the latest available carbon intensity value for a region."""
        data = self._get(region)
        entries = self._build_entries(data, region.upper())

        if not entries:
            raise HTTPException(status_code=404, detail="No EnergyCharts data available")

        return [entries[-1]]

    def get_historical(self, region: str, start_time: datetime = None, end_time: datetime = None) -> List[dict]:
        """Get historical carbon intensity data for a region and time range."""
        if start_time is None:
            start_time = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        if end_time is None:
            end_time = datetime.now(tz=timezone.utc)

        data = self._get(region)
        entries = self._build_entries(data, region.upper())

        return [entry for entry in entries if start_time <= entry["time"] <= end_time]
