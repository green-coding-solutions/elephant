"""Tests for the EnergyCharts provider."""

from datetime import datetime, timezone

from elephant.config import ProviderConfig
from elephant.providers.energycharts import EnergyChartsProvider, PROVIDER_NAME


def _sample_response() -> dict:
    return {
        "unix_seconds": [1000, 2000, 3000],
        "co2eq": [10.0, None, 30.0],
        "co2eq_forecast": [None, 20.0, None],
    }


def test_get_historical_merges_forecast(monkeypatch) -> None:
    """Historical values include measured and forecast data."""
    provider = EnergyChartsProvider(ProviderConfig())
    monkeypatch.setattr(provider, "_get", lambda region: _sample_response())

    start = datetime.fromtimestamp(0, tz=timezone.utc)
    end = datetime.fromtimestamp(4000, tz=timezone.utc)

    results = provider.get_historical("DE", start_time=start, end_time=end)

    assert len(results) == 3
    assert results[0]["carbon_intensity"] == 10.0
    assert results[1]["carbon_intensity"] == 20.0  # pulled from forecast fallback
    assert all(entry["provider"] == PROVIDER_NAME for entry in results)


def test_get_current_returns_latest(monkeypatch) -> None:
    """Current value returns the most recent timestamp."""
    provider = EnergyChartsProvider(ProviderConfig())
    monkeypatch.setattr(provider, "_get", lambda region: _sample_response())

    result = provider.get_current("DE")

    assert len(result) == 1
    assert result[0]["time"] == datetime.fromtimestamp(3000, tz=timezone.utc)
    assert result[0]["carbon_intensity"] == 30.0


def test_resolution_can_be_overridden(monkeypatch) -> None:
    """Provider uses configured resolution in emitted entries."""
    provider = EnergyChartsProvider(ProviderConfig(resolution="hourly"))
    monkeypatch.setattr(provider, "_get", lambda region: _sample_response())

    result = provider.get_current("DE")

    assert result[0]["resolution"] == "hourly"
