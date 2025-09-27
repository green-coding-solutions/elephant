"""ElectricityMaps provider for carbon intensity data."""

import logging
from typing import List, NoReturn
from datetime import datetime

import httpx
from fastapi import HTTPException

from .base import CarbonIntensityProvider
from ..models import CarbonIntensityResponse, ElectricityMapsResponse
from ..config import ProviderConfig
from ..utils.time_range_filter import TimeRangeFilter


logger = logging.getLogger(__name__)


class ElectricityMapsProvider(CarbonIntensityProvider):
    """Provider for ElectricityMaps carbon intensity data."""

    def __init__(self, config: ProviderConfig):
        self.config = config
        headers = {"auth-token": config.api_token} if config.api_token else {}
        self.client = httpx.AsyncClient(base_url=config.base_url, headers=headers, timeout=30.0)

    def _handle_http_error(self, error: httpx.HTTPStatusError) -> NoReturn:
        """Handle HTTP errors from ElectricityMaps API."""
        logger.error("ElectricityMaps API error: %s - %s", error.response.status_code, error.response.text)

        # Try to extract meaningful error from JSON response
        try:
            error_data = error.response.json()
            error_message = error_data.get("message", error_data.get("error", str(error_data)))
        except (ValueError, KeyError):
            error_message = error.response.text

        # Map ElectricityMaps status codes to appropriate HTTP responses
        status_mappings = {
            400: (400, f"ElectricityMaps invalid request: {error_message}"),
            401: (401, f"ElectricityMaps authentication failed: {error_message}"),
            403: (403, f"ElectricityMaps access denied: {error_message}"),
            404: (404, f"ElectricityMaps resource not found: {error_message}"),
            429: (429, "Rate limit exceeded"),
        }

        if error.response.status_code in status_mappings:
            status_code, detail = status_mappings[error.response.status_code]
        elif 400 <= error.response.status_code < 500:
            status_code, detail = 400, f"ElectricityMaps client error: {error_message}"
        else:
            status_code, detail = 503, f"ElectricityMaps service temporarily unavailable: {error_message}"

        raise HTTPException(status_code=status_code, detail=detail)

    def _handle_request_error(self, error: httpx.RequestError) -> NoReturn:
        """Handle request errors from ElectricityMaps API."""
        logger.error("ElectricityMaps request error: %s", error)
        raise HTTPException(status_code=503, detail="ElectricityMaps service temporarily unavailable")

    async def get_current(self, location: str) -> CarbonIntensityResponse:
        """Get current carbon intensity for a location."""
        try:
            response = await self.client.get("/v3/carbon-intensity/latest", params={"zone": location})
            response.raise_for_status()

            data = ElectricityMapsResponse(**response.json())

            return CarbonIntensityResponse(location=location, time=data.datetime, carbon_intensity=data.carbonIntensity)

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
        except httpx.RequestError as e:
            self._handle_request_error(e)

    async def get_historical(
        self, location: str, start_time: datetime, end_time: datetime, interpolate: bool = False
    ) -> List[CarbonIntensityResponse]:
        """Get historical carbon intensity data for a location and time range."""
        try:
            # ElectricityMaps history endpoint only returns last 24 hours
            response = await self.client.get(
                "/v3/carbon-intensity/history",
                params={"zone": location},
            )
            response.raise_for_status()

            history_data = response.json().get("history", [])

            # Convert to CarbonIntensityResponse objects
            all_data = []
            for item in history_data:
                item_time = datetime.fromisoformat(item["datetime"].replace("Z", "+00:00"))
                all_data.append(
                    CarbonIntensityResponse(
                        location=location,
                        time=item_time,
                        carbon_intensity=item["carbonIntensity"],
                    )
                )

            # Use TimeRangeFilter to filter data based on the requested time range and interpolation mode
            return TimeRangeFilter.filter_data(all_data, start_time, end_time, interpolate)

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
        except httpx.RequestError as e:
            self._handle_request_error(e)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
