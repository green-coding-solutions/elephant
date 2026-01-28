"""Tests for provider helper selection."""

import pytest
from elephant.providers import helpers
from elephant.config import Config, ProviderConfig, DatabaseConfig, CronConfig, LoggingConfig, Source


def make_config(sources: list[Source], providers: dict | None = None) -> Config:
    """Build a Config with the given cron sources."""
    return Config(
        database=DatabaseConfig(url="postgresql://user:pass@localhost:5432/elephant"),
        providers=providers or {},
        cron=CronConfig(sources=sources),
        logging=LoggingConfig(level="INFO"),
    )


def test_get_providers_follows_cron_sources(monkeypatch) -> None:
    """Providers returned only for those referenced in cron sources."""
    cfg = make_config(
        sources=[
            Source(region="DE", provider="electricitymaps"),
            Source(region="FR", provider="energycharts"),
        ],
        providers={"electricitymaps": ProviderConfig(api_token="token")},
    )
    monkeypatch.setattr(helpers, "config", cfg)

    providers = helpers.get_providers()

    assert set(providers.keys()) == {"electricitymaps_de", "energycharts_fr"}
    assert isinstance(providers["electricitymaps_de"], helpers.ElectricityMapsProvider)


def test_get_providers_deduplicates_and_skips_unknown(monkeypatch) -> None:
    """Duplicate cron entries are collapsed and unknown providers ignored."""
    cfg = make_config(
        sources=[
            Source(region="DE", provider="energycharts"),
            Source(region="DE", provider="energycharts"),
        ]
    )
    monkeypatch.setattr(helpers, "config", cfg)

    providers = helpers.get_providers()

    assert set(providers.keys()) == {"energycharts_de"}

def test_unknown_provider(monkeypatch) -> None:
    """Duplicate cron entries are collapsed and unknown providers ignored."""
    cfg = make_config(
        sources=[
            Source(region="DE", provider="energycharts"),
            Source(region="DE", provider="unknown"),
        ]
    )
    monkeypatch.setattr(helpers, "config", cfg)

    with pytest.raises(ValueError):
        helpers.get_providers()
