"""Tests for cron source fetch mode selection."""

from contextlib import contextmanager
from datetime import datetime, timezone

from elephant import cron as cron_module
from elephant.config import Config, CronConfig, DatabaseConfig, LoggingConfig, Source


class _FakeCursor:
    def __init__(self) -> None:
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _sql, _params=None) -> None:
        self.rowcount = 1


class _FakeConnection:
    def __init__(self) -> None:
        self.commits = 0

    def cursor(self):
        return _FakeCursor()

    def commit(self) -> None:
        self.commits += 1


class _CountingProvider:
    def __init__(self) -> None:
        self.current_calls = 0
        self.historical_calls = 0
        self.future_calls = 0

    def get_current(self, region: str):
        self.current_calls += 1
        return [
            {
                "region": region,
                "time": datetime.now(tz=timezone.utc),
                "carbon_intensity": 100.0,
                "provider": "energycharts",
                "resolution": "15_minutes",
                "estimation": False,
            }
        ]

    def get_historical(self, region: str):
        self.historical_calls += 1
        return [
            {
                "region": region,
                "time": datetime.now(tz=timezone.utc),
                "carbon_intensity": 95.0,
                "provider": "energycharts",
                "resolution": "15_minutes",
                "estimation": False,
            }
        ]

    def get_future(self, _region: str):
        self.future_calls += 1
        return []


def _make_config(source: Source) -> Config:
    return Config(
        database=DatabaseConfig(url="postgresql://user:pass@localhost:5432/elephant"),
        cron=CronConfig(sources=[source]),
        logging=LoggingConfig(level="INFO"),
    )


def test_run_cron_uses_current_when_only_get_current_enabled(monkeypatch) -> None:
    provider = _CountingProvider()
    cfg = _make_config(Source(region="DE", provider="energycharts", only_get_current=True))
    conn = _FakeConnection()

    @contextmanager
    def _fake_db_connection():
        yield conn

    monkeypatch.setattr(cron_module, "config", cfg)
    monkeypatch.setattr(cron_module, "get_providers", lambda: {"energycharts_de": provider})
    monkeypatch.setattr(cron_module, "db_connection", _fake_db_connection)

    cron_module.run_cron()

    assert provider.current_calls == 1
    assert provider.historical_calls == 0
    assert provider.future_calls == 0
    assert conn.commits == 1


def test_run_cron_uses_historical_by_default(monkeypatch) -> None:
    provider = _CountingProvider()
    cfg = _make_config(Source(region="DE", provider="energycharts"))
    conn = _FakeConnection()

    @contextmanager
    def _fake_db_connection():
        yield conn

    monkeypatch.setattr(cron_module, "config", cfg)
    monkeypatch.setattr(cron_module, "get_providers", lambda: {"energycharts_de": provider})
    monkeypatch.setattr(cron_module, "db_connection", _fake_db_connection)

    cron_module.run_cron()

    assert provider.current_calls == 0
    assert provider.historical_calls == 1
    assert provider.future_calls == 1
    assert conn.commits == 1
