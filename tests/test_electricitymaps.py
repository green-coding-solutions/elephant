"""Tests for the ElectricityMaps provider."""

from elephant.config import ProviderConfig
from elephant.providers.electricitymaps import ElectricityMapsProvider


class _FakeResponse:
    def json(self) -> dict:
        return {
            "datetime": "2024-01-01T00:00:00Z",
            "carbonIntensity": 123.0,
            "isEstimated": False,
        }


def test_resolution_can_be_overridden(monkeypatch) -> None:
    """Provider uses configured resolution for API requests and output entries."""
    provider = ElectricityMapsProvider(ProviderConfig(api_token="token", resolution="15_minutes"))
    captured = {}

    def fake_get(path: str, params: dict):
        captured["path"] = path
        captured["params"] = params
        return _FakeResponse()

    monkeypatch.setattr(provider, "_get", fake_get)

    result = provider.get_current("DE")

    assert captured["path"] == "/v3/carbon-intensity/latest"
    assert captured["params"]["temporalGranularity"] == "15_minutes"
    assert result[0]["resolution"] == "15_minutes"
