"""Tests for provider helper selection."""

import pytest

from elephant.providers import helpers
from elephant.config import Config, ProviderConfig, DatabaseConfig, CronConfig, LoggingConfig


def make_config(providers: dict) -> Config:
    """Build a Config with the given providers enabled/disabled."""
    return Config(
        database=DatabaseConfig(url="postgresql://user:pass@localhost:5432/elephant"),
        providers=providers,
        cron=CronConfig(),
        logging=LoggingConfig(level="INFO"),
    )


def test_get_providers_includes_enabled_only(monkeypatch) -> None:
    """Enabled providers are returned; disabled ones are skipped."""
    cfg = make_config(
        {
            "electricitymaps": ProviderConfig(enabled=True),
            "energycharts": ProviderConfig(enabled=False),
            "bundesnetzagentur": ProviderConfig(enabled=False),
            "bundesnetzagentur_all": ProviderConfig(enabled=False),
        }
    )
    monkeypatch.setattr(helpers, "config", cfg)

    providers = helpers.get_providers()
    assert set(providers.keys()) == {"electricitymaps"}


def test_get_providers_energycharts_only(monkeypatch) -> None:
    """EnergyCharts provider is returned when enabled by itself."""
    cfg = make_config(
        {
            "electricitymaps": ProviderConfig(enabled=False),
            "energycharts": ProviderConfig(enabled=True),
            "bundesnetzagentur": ProviderConfig(enabled=False),
            "bundesnetzagentur_all": ProviderConfig(enabled=False),
        }
    )
    monkeypatch.setattr(helpers, "config", cfg)

    providers = helpers.get_providers()
    assert set(providers.keys()) == {"energycharts"}


def test_get_providers_handles_multiple(monkeypatch) -> None:
    """Multiple enabled providers are all returned."""
    cfg = make_config(
        {
            "electricitymaps": ProviderConfig(enabled=True),
            "energycharts": ProviderConfig(enabled=True),
            "bundesnetzagentur": ProviderConfig(enabled=True),
            "bundesnetzagentur_all": ProviderConfig(enabled=True),
        }
    )
    monkeypatch.setattr(helpers, "config", cfg)

    providers = helpers.get_providers()
    assert set(providers.keys()) == {"electricitymaps", "energycharts", "bundesnetzagentur", "bundesnetzagentur_all"}


def test_get_providers_all_disabled(monkeypatch) -> None:
    """If all providers disabled, empty dict is returned."""
    cfg = make_config(
        {
            "electricitymaps": ProviderConfig(enabled=False),
            "energycharts": ProviderConfig(enabled=False),
            "bundesnetzagentur": ProviderConfig(enabled=False),
            "bundesnetzagentur_all": ProviderConfig(enabled=False),
        }
    )
    monkeypatch.setattr(helpers, "config", cfg)

    providers = helpers.get_providers()
    assert providers == {}
