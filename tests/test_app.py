"""Tests for the main FastAPI application."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from typing import Any

from elephant.app import app
from elephant.models import CarbonIntensityResponse
from datetime import datetime


@pytest.fixture(name="test_client")
def fixture_test_client() -> TestClient:
    """Test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(name="mock_carbon_provider")
def fixture_mock_carbon_provider() -> AsyncMock:
    """Mock provider for testing."""
    provider = AsyncMock()
    provider.get_current.return_value = CarbonIntensityResponse(
        location="DE", time=datetime.fromisoformat("2025-09-22T10:45:00+00:00"), carbon_intensity=241.0
    )
    provider.get_historical.return_value = [
        CarbonIntensityResponse(
            location="DE", time=datetime.fromisoformat("2025-09-22T10:00:00+00:00"), carbon_intensity=241.0
        ),
        CarbonIntensityResponse(
            location="DE", time=datetime.fromisoformat("2025-09-22T11:00:00+00:00"), carbon_intensity=235.0
        ),
    ]
    return provider


class TestCarbonIntensityEndpoint:
    """Tests for the current carbon intensity endpoint."""

    def test_health_check(self, test_client: TestClient) -> None:
        """Test health check endpoint."""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "providers" in data

    @patch("elephant.app.carbon_providers")
    def test_get_current_success(
        self, mock_providers: Any, test_client: TestClient, mock_carbon_provider: AsyncMock
    ) -> None:
        """Test successful current carbon intensity request."""
        mock_providers.__getitem__.return_value = mock_carbon_provider
        mock_providers.__contains__.return_value = True

        response = test_client.get("/carbon-intensity/current?location=DE")

        assert response.status_code == 200
        data = response.json()
        assert data["location"] == "DE"
        assert data["carbon_intensity"] == 241.0
        assert "time" in data

    def test_missing_location_parameter(self, test_client: TestClient) -> None:
        """Test request without location parameter."""
        response = test_client.get("/carbon-intensity/current")

        assert response.status_code == 422  # FastAPI validation error

    def test_invalid_location_format(self, test_client: TestClient) -> None:
        """Test request with invalid location format."""
        response = test_client.get("/carbon-intensity/current?location=INVALID")

        assert response.status_code == 400
        assert "country code" in response.json()["detail"]

    def test_single_character_location(self, test_client: TestClient) -> None:
        """Test request with single character location."""
        response = test_client.get("/carbon-intensity/current?location=D")

        assert response.status_code == 400
        assert "country code" in response.json()["detail"]

    def test_numeric_location(self, test_client: TestClient) -> None:
        """Test request with numeric location."""
        response = test_client.get("/carbon-intensity/current?location=12")

        assert response.status_code == 400
        assert "country code" in response.json()["detail"]

    @patch("elephant.app.carbon_providers")
    def test_no_providers_available(self, mock_providers: Any, test_client: TestClient) -> None:
        """Test when no providers are available."""
        mock_providers.__contains__.return_value = False

        response = test_client.get("/carbon-intensity/current?location=DE")

        assert response.status_code == 503
        assert "No carbon intensity providers available" in response.json()["detail"]
        assert "simulation endpoints" in response.json()["detail"]


class TestCarbonIntensityHistoryEndpoint:
    """Tests for the carbon intensity history endpoint."""

    @patch("elephant.app.carbon_providers")
    def test_get_history_success(
        self, mock_providers: Any, test_client: TestClient, mock_carbon_provider: AsyncMock
    ) -> None:
        """Test successful historical carbon intensity request."""
        mock_providers.__getitem__.return_value = mock_carbon_provider
        mock_providers.__contains__.return_value = True

        response = test_client.get(
            "/carbon-intensity/history?location=DE&startTime=2025-09-22T10:00:00Z&endTime=2025-09-22T12:00:00Z"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["location"] == "DE"
        assert data[0]["carbon_intensity"] == 241.0
        assert data[1]["location"] == "DE"
        assert data[1]["carbon_intensity"] == 235.0
        assert "time" in data[0]
        assert "time" in data[1]

    def test_missing_location_parameter(self, test_client: TestClient) -> None:
        """Test request without location parameter."""
        response = test_client.get(
            "/carbon-intensity/history?startTime=2025-09-22T10:00:00Z&endTime=2025-09-22T12:00:00Z"
        )

        assert response.status_code == 422  # FastAPI validation error

    def test_missing_start_time_parameter(self, test_client: TestClient) -> None:
        """Test request without startTime parameter."""
        response = test_client.get("/carbon-intensity/history?location=DE&endTime=2025-09-22T12:00:00Z")

        assert response.status_code == 422  # FastAPI validation error

    def test_missing_end_time_parameter(self, test_client: TestClient) -> None:
        """Test request without endTime parameter."""
        response = test_client.get("/carbon-intensity/history?location=DE&startTime=2025-09-22T10:00:00Z")

        assert response.status_code == 422  # FastAPI validation error

    def test_invalid_location_format(self, test_client: TestClient) -> None:
        """Test request with invalid location format."""
        response = test_client.get(
            "/carbon-intensity/history?location=INVALID&startTime=2025-09-22T10:00:00Z&endTime=2025-09-22T12:00:00Z"
        )

        assert response.status_code == 400
        assert "country code" in response.json()["detail"]

    def test_invalid_start_time_format(self, test_client: TestClient) -> None:
        """Test request with invalid startTime format."""
        response = test_client.get(
            "/carbon-intensity/history?location=DE&startTime=invalid-date&endTime=2025-09-22T12:00:00Z"
        )

        assert response.status_code == 400
        assert "Invalid datetime format" in response.json()["detail"]

    def test_invalid_end_time_format(self, test_client: TestClient) -> None:
        """Test request with invalid endTime format."""
        response = test_client.get(
            "/carbon-intensity/history?location=DE&startTime=2025-09-22T10:00:00Z&endTime=invalid-date"
        )

        assert response.status_code == 400
        assert "Invalid datetime format" in response.json()["detail"]

    def test_start_time_after_end_time(self, test_client: TestClient) -> None:
        """Test request where startTime is after endTime."""
        response = test_client.get(
            "/carbon-intensity/history?location=DE&startTime=2025-09-22T12:00:00Z&endTime=2025-09-22T10:00:00Z"
        )

        assert response.status_code == 400
        assert "startTime must be before endTime" in response.json()["detail"]

    def test_start_time_equals_end_time(self, test_client: TestClient) -> None:
        """Test request where startTime equals endTime."""
        response = test_client.get(
            "/carbon-intensity/history?location=DE&startTime=2025-09-22T10:00:00Z&endTime=2025-09-22T10:00:00Z"
        )

        assert response.status_code == 400
        assert "startTime must be before endTime" in response.json()["detail"]

    @patch("elephant.app.carbon_providers")
    def test_no_providers_available(self, mock_providers: Any, test_client: TestClient) -> None:
        """Test when no providers are available."""
        mock_providers.__contains__.return_value = False

        response = test_client.get(
            "/carbon-intensity/history?location=DE&startTime=2025-09-22T10:00:00Z&endTime=2025-09-22T12:00:00Z"
        )

        assert response.status_code == 503
        assert "No carbon intensity providers available" in response.json()["detail"]
        assert "simulation endpoints" in response.json()["detail"]

    def test_datetime_with_plus_timezone(self, test_client: TestClient) -> None:
        """Test that datetime with +00:00 timezone works."""
        with patch("elephant.app.carbon_providers") as mock_providers:
            mock_provider = AsyncMock()
            mock_provider.get_historical.return_value = []
            mock_providers.__getitem__.return_value = mock_provider
            mock_providers.__contains__.return_value = True

            # URL encode the + character as %2B
            response = test_client.get(
                "/carbon-intensity/history?location=DE&startTime=2025-09-22T10:00:00%2B00:00&endTime=2025-09-22T12:00:00%2B00:00"
            )

            assert response.status_code == 200

    def test_datetime_without_timezone(self, test_client: TestClient) -> None:
        """Test that datetime without timezone works."""
        with patch("elephant.app.carbon_providers") as mock_providers:
            mock_provider = AsyncMock()
            mock_provider.get_historical.return_value = []
            mock_providers.__getitem__.return_value = mock_provider
            mock_providers.__contains__.return_value = True

            response = test_client.get(
                "/carbon-intensity/history?location=DE&startTime=2025-09-22T10:00:00&endTime=2025-09-22T12:00:00"
            )

            assert response.status_code == 200
