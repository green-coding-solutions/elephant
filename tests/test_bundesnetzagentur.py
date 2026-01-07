"""Integration-style tests for Bundesnetzagentur provider."""

from datetime import datetime, timezone

from elephant.providers.bundesnetzagentur import BundesnetzagenturProvider
from elephant.config import ProviderConfig


def test_get_current_returns_expected_format():
    """Ensure Bundesnetzagentur provider returns a list of dicts with required keys."""
    provider = BundesnetzagenturProvider(ProviderConfig(enabled=True))

    result = provider.get_current("DE")

    assert result is None or isinstance(result, list)

    if result:
        entry = result[0]
        assert set(entry.keys()) == {"region", "time", "carbon_intensity", "provider", "resolution", "estimation"}
        assert entry["region"] == "DE"
        assert isinstance(entry["time"], datetime)

        assert entry["time"].tzinfo is not None
        assert isinstance(entry["carbon_intensity"], (int, float))
        assert entry["provider"] == "bundesnetzagentur"
