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
        """Test successful historical data request with 24h hourly data and time filtering."""
        # Mock 24 hours of hourly data (as ElectricityMaps returns)
        base_time = datetime.fromisoformat("2025-09-22T00:00:00+00:00")
        history_data = []

        for hour in range(24):
            timestamp = base_time.replace(hour=hour)
            history_data.append(
                {
                    "datetime": timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "carbonIntensity": 200.0 + hour * 2.0,  # Varying intensity values
                }
            )

        mock_response_data = {"history": history_data}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        # Request data for a specific 4-hour window (08:00-12:00)
        start_time = datetime.fromisoformat("2025-09-22T08:00:00+00:00")
        end_time = datetime.fromisoformat("2025-09-22T12:00:00+00:00")

        with patch.object(electricitymaps_provider.client, "get", return_value=mock_response):
            result = await electricitymaps_provider.get_historical("DE", start_time, end_time)

            # Should only return data within the requested time range (4 hours: 08:00, 09:00, 10:00, 11:00)
            assert len(result) == 4
            assert all(isinstance(item, CarbonIntensityResponse) for item in result)

            # Verify all returned data is within the requested time range
            for item in result:
                assert start_time <= item.time < end_time
                assert item.location == "DE"

            # Verify specific values for the filtered time range
            assert result[0].carbonIntensity == 216.0  # 200.0 + 8 * 2.0 (hour 8)
            assert result[1].carbonIntensity == 218.0  # 200.0 + 9 * 2.0 (hour 9)
            assert result[2].carbonIntensity == 220.0  # 200.0 + 10 * 2.0 (hour 10)
            assert result[3].carbonIntensity == 222.0  # 200.0 + 11 * 2.0 (hour 11)

    @pytest.mark.asyncio
    async def test_get_historical_filters_time_range_correctly(
        self, electricitymaps_provider: ElectricityMapsProvider
    ) -> None:
        """Test that historical data is correctly filtered to only return data within the requested time range."""
        # Mock 24 hours of hourly data starting from midnight
        base_time = datetime.fromisoformat("2025-09-22T00:00:00+00:00")
        history_data = []

        for hour in range(24):
            timestamp = base_time.replace(hour=hour)
            history_data.append(
                {
                    "datetime": timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "carbonIntensity": 100.0 + hour,  # Simple incrementing values
                }
            )

        mock_response_data = {"history": history_data}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        # Test case 1: Request data outside the available range (should return empty)
        start_time = datetime.fromisoformat("2025-09-23T01:00:00+00:00")  # Next day
        end_time = datetime.fromisoformat("2025-09-23T05:00:00+00:00")

        with patch.object(electricitymaps_provider.client, "get", return_value=mock_response):
            result = await electricitymaps_provider.get_historical("DE", start_time, end_time)
            assert len(result) == 0

        # Test case 2: Request data that partially overlaps (should return only overlapping hours)
        start_time = datetime.fromisoformat("2025-09-22T22:00:00+00:00")  # Last 2 hours of day
        end_time = datetime.fromisoformat("2025-09-23T02:00:00+00:00")  # 2 hours into next day

        with patch.object(electricitymaps_provider.client, "get", return_value=mock_response):
            result = await electricitymaps_provider.get_historical("DE", start_time, end_time)

            # Should only return hours 22 and 23 (within available data)
            assert len(result) == 2
            assert result[0].carbonIntensity == 122.0  # 100.0 + 22
            assert result[1].carbonIntensity == 123.0  # 100.0 + 23

        # Test case 3: Request exact boundary (inclusive start, exclusive end)
        start_time = datetime.fromisoformat("2025-09-22T05:00:00+00:00")
        end_time = datetime.fromisoformat("2025-09-22T05:00:00+00:00")  # Same time (empty range)

        with patch.object(electricitymaps_provider.client, "get", return_value=mock_response):
            result = await electricitymaps_provider.get_historical("DE", start_time, end_time)
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_historical_with_interpolation(self, electricitymaps_provider: ElectricityMapsProvider) -> None:
        """Test that interpolation parameter is properly passed to TimeRangeFilter."""
        mock_response_data = {
            "history": [
                {"datetime": "2025-09-22T10:00:00.000Z", "carbonIntensity": 241.0},
                {"datetime": "2025-09-22T11:00:00.000Z", "carbonIntensity": 235.0},
            ]
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        start_time = datetime.fromisoformat("2025-09-22T10:15:00+00:00")
        end_time = datetime.fromisoformat("2025-09-22T10:45:00+00:00")

        with patch.object(electricitymaps_provider.client, "get", return_value=mock_response):
            # Test that interpolate=True works (TimeRangeFilter details tested separately)
            result = await electricitymaps_provider.get_historical("DE", start_time, end_time, interpolate=True)

            # Verify provider correctly converts API response to CarbonIntensityResponse objects
            assert len(result) == 2
            assert all(
                hasattr(item, "location") and hasattr(item, "time") and hasattr(item, "carbonIntensity")
                for item in result
            )
            assert all(item.location == "DE" for item in result)
