"""Tests for the EnergyCharts provider."""

from datetime import datetime, timedelta, timezone

from elephant.config import ProviderConfig
from elephant.providers import energycharts
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
    monkeypatch.setattr(provider, "_get", lambda region, start_time=None, end_time=None: _sample_response())

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
    monkeypatch.setattr(provider, "_get", lambda region, start_time=None, end_time=None: _sample_response())

    result = provider.get_current("DE")

    assert len(result) == 1
    assert result[0]["time"] == datetime.fromtimestamp(3000, tz=timezone.utc)
    assert result[0]["carbon_intensity"] == 30.0


def test_resolution_can_be_overridden(monkeypatch) -> None:
    """Provider uses configured resolution in emitted entries."""
    provider = EnergyChartsProvider(ProviderConfig(resolution="hourly"))
    monkeypatch.setattr(provider, "_get", lambda region, start_time=None, end_time=None: _sample_response())

    result = provider.get_current("DE")

    assert result[0]["resolution"] == "hourly"


def test_get_historical_requests_seven_days_by_default(monkeypatch) -> None:
    """Without a range, cron re-fetches the last seven days so corrections overwrite stored values."""
    captured = {}
    provider = EnergyChartsProvider(ProviderConfig())

    def fake_get(region, start_time=None, end_time=None):
        captured.update(start=start_time, end=end_time)
        return _sample_response()

    monkeypatch.setattr(provider, "_get", fake_get)
    end = datetime(2024, 1, 8, tzinfo=timezone.utc)

    provider.get_historical("DE", end_time=end)

    assert captured == {"start": end - timedelta(days=7), "end": end}


def test_request_parameters(monkeypatch) -> None:
    """The time range is sent to the API in UTC."""
    captured = {}

    class _Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return _sample_response()

    def fake_get(url, params, timeout):
        captured.update(url=url, params=params)
        return _Response()

    monkeypatch.setattr(energycharts.requests, "get", fake_get)
    start = datetime(2024, 1, 1, 1, 0, tzinfo=timezone(timedelta(hours=1)))
    end = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)

    EnergyChartsProvider(ProviderConfig()).get_historical("DE", start_time=start, end_time=end)

    assert captured["params"] == {"country": "de", "start": "2024-01-01T00:00Z", "end": "2024-01-08T00:00Z"}


def test_get_future_requests_without_range(monkeypatch) -> None:
    """The forecast comes from the default response, which includes tomorrow."""
    captured = {}
    provider = EnergyChartsProvider(ProviderConfig())

    def fake_get(region, start_time=None, end_time=None):
        captured.update(start=start_time, end=end_time)
        return _sample_response()

    monkeypatch.setattr(provider, "_get", fake_get)

    provider.get_future("DE")

    assert captured == {"start": None, "end": None}
