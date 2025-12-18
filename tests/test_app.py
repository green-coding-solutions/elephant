"""Tests for FastAPI application endpoints."""

import pytest
from fastapi import HTTPException

from elephant import app as app_module
from elephant.app import (
    get_primary_carbon_intensity,
    get_current_carbon_intensity,
    get_carbon_intensity_history,
    list_regions,
    health_check,
    index,
)
from elephant.config import Config, CronConfig, DatabaseConfig, LoggingConfig, ProviderConfig, Source


def _make_config(primary_provider: str = "electricitymaps") -> Config:
    """Helper to build a minimal Config for tests."""
    return Config(
        database=DatabaseConfig(url="postgresql://user:pass@localhost:5432/elephant"),
        providers={
            "electricitymaps": ProviderConfig(enabled=True),
            "bundesnetzagentur": ProviderConfig(enabled=True),
        },
        cron=CronConfig(
            interval_seconds=300,
            sources=[
                Source(region="DE", provider=primary_provider, primary=True),
                Source(region="DE", provider="bundesnetzagentur", primary=False),
            ],
        ),
        logging=LoggingConfig(level="INFO"),
    )


@pytest.mark.asyncio
async def test_index_returns_html() -> None:
    """Index endpoint returns HTML content."""
    response = await index()
    assert response.status_code == 200
    assert response.media_type == "text/html"
    assert b"<html" in response.body.lower()


@pytest.mark.asyncio
async def test_list_regions(monkeypatch) -> None:
    """Regions endpoint returns DB regions."""
    monkeypatch.setattr(app_module, "fetch_regions", lambda db: ["DE", "FR"])
    regions = await list_regions(db=object())
    assert regions == ["DE", "FR"]


@pytest.mark.asyncio
async def test_get_current_carbon_intensity_success(monkeypatch) -> None:
    """Current endpoint returns latest data."""
    monkeypatch.setattr(app_module, "fetch_latest", lambda db, region: {"provider": {"carbon_intensity": 123}})
    result = await get_current_carbon_intensity(region="DE", update=False, db=object())
    assert result["provider"]["carbon_intensity"] == 123


@pytest.mark.asyncio
async def test_get_current_carbon_intensity_triggers_update(monkeypatch) -> None:
    """Current endpoint triggers cron when update=True."""
    called = {}

    async def fake_run_in_threadpool(func, region=None):
        called["region"] = region
        return None

    monkeypatch.setattr(app_module, "run_in_threadpool", fake_run_in_threadpool)
    monkeypatch.setattr(app_module, "fetch_latest", lambda db, region: {"provider": {"carbon_intensity": 1}})

    await get_current_carbon_intensity(region="FR", update=True, db=object())
    assert called["region"] == "FR"


@pytest.mark.asyncio
async def test_get_current_carbon_intensity_not_found(monkeypatch) -> None:
    """Current endpoint raises 404 when no data."""
    monkeypatch.setattr(app_module, "fetch_latest", lambda db, region: {})
    with pytest.raises(HTTPException) as exc:
        await get_current_carbon_intensity(region="DE", update=False, db=object())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_primary_carbon_intensity_returns_primary(monkeypatch) -> None:
    """Primary endpoint returns only the configured primary provider entry."""
    app_module.config = _make_config(primary_provider="electricitymaps")

    # Stub fetch_latest to simulate DB results
    monkeypatch.setattr(
        app_module,
        "fetch_latest",
        lambda db, region: {
            "electricitymaps_de": {"time": "t1", "carbon_intensity": 111},
            "bundesnetzagentur": {"time": "t2", "carbon_intensity": 222},
        },
    )

    result = await get_primary_carbon_intensity(region="DE", update=False, db=object())
    assert list(result.keys()) == ["electricitymaps_de"]
    assert result["electricitymaps_de"]["carbon_intensity"] == 111


@pytest.mark.asyncio
async def test_get_primary_carbon_intensity_missing_primary_data(monkeypatch) -> None:
    """Primary endpoint raises 404 when primary provider has no data."""
    app_module.config = _make_config(primary_provider="electricitymaps")

    monkeypatch.setattr(
        app_module,
        "fetch_latest",
        lambda db, region: {
            "bundesnetzagentur": {"time": "t2", "carbon_intensity": 222},
        },
    )

    with pytest.raises(HTTPException) as exc:
        await get_primary_carbon_intensity(region="DE", update=False, db=object())

    assert exc.value.status_code == 404
    assert "primary provider" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_get_carbon_intensity_history(monkeypatch) -> None:
    """History endpoint returns windowed data."""
    sample = [{"time": "t1"}, {"time": "t2"}]
    monkeypatch.setattr(app_module, "fetch_between", lambda db, region, start, end: sample)
    result = await get_carbon_intensity_history(
        region="DE", startTime="2025-09-22T10:00:00Z", endTime="2025-09-22T12:00:00Z", db=object()
    )
    assert result == sample


@pytest.mark.asyncio
async def test_health_check(monkeypatch) -> None:
    """Health endpoint reports providers and record count."""
    monkeypatch.setattr(app_module, "get_providers", lambda: {"p1": object(), "p2": object()})

    class DummyCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return (5,)

        def fetchall(self):
            return [{"region": "DE"}, {"region": "FR"}]

    class DummyDB:
        def cursor(self, *args, **kwargs):
            return DummyCursor()

    result = await health_check(db=DummyDB())
    assert result["providers"] == ["p1", "p2"]
    assert result["db_records"] == 5
    assert result["regions"] == ["DE", "FR"]
