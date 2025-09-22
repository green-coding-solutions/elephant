"""ElectricityMaps provider for carbon intensity data."""

import logging
from typing import List, NoReturn
from datetime import datetime

import httpx
from fastapi import HTTPException

from .base import CarbonIntensityProvider
from ..models import CarbonIntensityResponse, ElectricityMapsResponse
from ..config import ProviderConfig


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

        if error.response.status_code == 429:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        # Try to extract meaningful error from JSON response
        try:
            error_data = error.response.json()
            error_message = error_data.get("message", error_data.get("error", str(error_data)))
        except (ValueError, KeyError):
            error_message = error.response.text

        # Determine appropriate error message based on status code
        if error.response.status_code in [401, 403]:
            detail = f"ElectricityMaps configuration error: {error_message}"
        elif error.response.status_code == 400:
            detail = f"ElectricityMaps invalid request: {error_message}"
        else:
            detail = f"ElectricityMaps service temporarily unavailable: {error_message}"

        raise HTTPException(status_code=503, detail=detail)

    def _handle_request_error(self, error: httpx.RequestError) -> NoReturn:
        """Handle request errors from ElectricityMaps API."""
        logger.error("ElectricityMaps request error: %s", error)
        raise HTTPException(status_code=503, detail="ElectricityMaps service temporarily unavailable")

    async def get_current(self, location: str) -> CarbonIntensityResponse:
        """Get current carbon intensity for a location."""
        try:
            response = await self.client.get("/v3/carbon-intensity/latest", params={"zone": location})

            if response.status_code == 429:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")

            response.raise_for_status()

            data = ElectricityMapsResponse(**response.json())

            return CarbonIntensityResponse(location=location, time=data.datetime, carbon_intensity=data.carbonIntensity)

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
        except httpx.RequestError as e:
            self._handle_request_error(e)

    async def get_historical(
        self, location: str, start_time: datetime, end_time: datetime
    ) -> List[CarbonIntensityResponse]:
        """Get historical carbon intensity data for a location and time range."""
        try:
            # ElectricityMaps history endpoint only returns last 24 hours
            response = await self.client.get(
                "/v3/carbon-intensity/history",
                params={"zone": location},
            )

            if response.status_code == 429:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")

            response.raise_for_status()

            history_data = response.json().get("history", [])

            # Convert to CarbonIntensityResponse objects and filter by time range
            results = []
            for item in history_data:
                item_time = datetime.fromisoformat(item["datetime"].replace("Z", "+00:00"))

                # Filter to only include data within the requested time range
                if start_time <= item_time < end_time:
                    results.append(
                        CarbonIntensityResponse(
                            location=location,
                            time=item_time,
                            carbon_intensity=item["carbonIntensity"],
                        )
                    )

            return results

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
        except httpx.RequestError as e:
            self._handle_request_error(e)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
