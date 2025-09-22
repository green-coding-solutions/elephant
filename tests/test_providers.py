"""Tests for carbon intensity providers."""

import pytest
from unittest.mock import AsyncMock, patch, Mock
from datetime import datetime

import httpx
from fastapi import HTTPException

from elephant.providers.electricitymaps import ElectricityMapsProvider
from elephant.config import ProviderConfig
from elephant.models import CarbonIntensityResponse
from typing import Dict, Any


@pytest.fixture(name="provider_config")
def fixture_provider_config() -> ProviderConfig:
    """Provider configuration for testing."""
    return ProviderConfig(enabled=True, base_url="https://api.electricitymaps.com", api_token="test-token")


@pytest.fixture(name="electricitymaps_provider")
def fixture_electricitymaps_provider(
    provider_config: ProviderConfig,
) -> ElectricityMapsProvider:
    """ElectricityMaps provider instance for testing."""
    return ElectricityMapsProvider(provider_config)


@pytest.fixture(name="mock_response_data")
def fixture_mock_response_data() -> Dict[str, Any]:
    """Mock response data from ElectricityMaps API."""
    return {
        "zone": "DE",
        "carbonIntensity": 241.0,
        "datetime": "2025-09-22T08:00:00.000Z",
        "updatedAt": "2025-09-22T07:55:51.863Z",
        "createdAt": "2025-09-19T21:26:02.144Z",
        "emissionFactorType": "lifecycle",
        "isEstimated": True,
        "estimationMethod": "FORECASTS_HIERARCHY",
        "temporalGranularity": "hourly",
    }


class TestElectricityMapsProvider:
    """Tests for ElectricityMaps provider."""

    @pytest.mark.asyncio
    async def test_get_current_success(
        self, electricitymaps_provider: ElectricityMapsProvider, mock_response_data: Dict[str, Any]
    ) -> None:
        """Test successful current carbon intensity request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        with patch.object(electricitymaps_provider.client, "get", return_value=mock_response):
            result = await electricitymaps_provider.get_current("DE")

            assert isinstance(result, CarbonIntensityResponse)
            assert result.location == "DE"
            assert result.carbonIntensity == 241.0
            assert isinstance(result.time, datetime)

    @pytest.mark.asyncio
    async def test_get_current_rate_limit(self, electricitymaps_provider: ElectricityMapsProvider) -> None:
        """Test rate limit handling."""
        mock_response = AsyncMock()
        mock_response.status_code = 429

        with patch.object(electricitymaps_provider.client, "get", return_value=mock_response):
            with pytest.raises(HTTPException) as exc_info:
                await electricitymaps_provider.get_current("DE")

            assert exc_info.value.status_code == 429
            assert "Rate limit exceeded" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_current_http_error(self, electricitymaps_provider: ElectricityMapsProvider) -> None:
        """Test HTTP error handling."""
        with patch.object(electricitymaps_provider.client, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal server error"
            mock_response.json.return_value = {"error": "Internal server error"}

            mock_get.side_effect = httpx.HTTPStatusError("Server error", request=AsyncMock(), response=mock_response)

            with pytest.raises(HTTPException) as exc_info:
                await electricitymaps_provider.get_current("DE")

            assert exc_info.value.status_code == 503
            assert "temporarily unavailable" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_current_request_error(self, electricitymaps_provider: ElectricityMapsProvider) -> None:
        """Test request error handling."""
        with patch.object(electricitymaps_provider.client, "get") as mock_get:
            mock_get.side_effect = httpx.RequestError("Connection failed")

            with pytest.raises(HTTPException) as exc_info:
                await electricitymaps_provider.get_current("DE")

            assert exc_info.value.status_code == 503
            assert "temporarily unavailable" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_historical_success(self, electricitymaps_provider: ElectricityMapsProvider) -> None:
        """Test successful historical data request."""
        mock_response_data = {
            "history": [
                {"datetime": "2025-09-22T08:00:00.000Z", "carbonIntensity": 241.0},
                {"datetime": "2025-09-22T09:00:00.000Z", "carbonIntensity": 235.0},
            ]
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        start_time = datetime.fromisoformat("2025-09-22T08:00:00+00:00")
        end_time = datetime.fromisoformat("2025-09-22T10:00:00+00:00")

        with patch.object(electricitymaps_provider.client, "get", return_value=mock_response):
            result = await electricitymaps_provider.get_historical("DE", start_time, end_time)

            assert len(result) == 2
            assert all(isinstance(item, CarbonIntensityResponse) for item in result)
            assert result[0].carbonIntensity == 241.0
            assert result[1].carbonIntensity == 235.0
