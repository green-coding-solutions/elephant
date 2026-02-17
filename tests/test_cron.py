"""Tests for cron source fetch mode selection."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from elephant import cron as cron_module
from elephant.config import Config, CronConfig, DatabaseConfig, LoggingConfig, Source


class _FakeCursor:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.rowcount = 0
        self._fetchone = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _sql, _params=None) -> None:
        sql = " ".join(_sql.lower().split())

        if "select last_run from last_cron_run" in sql:
            source = _params[0]
            last_run = self.conn.last_runs.get(source)
            self._fetchone = (last_run,) if last_run is not None else None
            self.rowcount = 1 if last_run is not None else 0
            return

        if "insert into last_cron_run" in sql:
            source, last_run = _params
            self.conn.last_runs[source] = last_run
            self.rowcount = 1
            self._fetchone = None
            return

        self.rowcount = 1
        self._fetchone = None

    def fetchone(self):
        return self._fetchone


class _FakeConnection:
    def __init__(self) -> None:
        self.commits = 0
        self.last_runs = {}

    def cursor(self):
        return _FakeCursor(self)

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


def test_run_cron_skips_source_if_update_iterval_not_elapsed(monkeypatch) -> None:
    provider = _CountingProvider()
    cfg = _make_config(Source(region="DE", provider="energycharts", update_iterval=15))
    conn = _FakeConnection()
    conn.last_runs["energycharts_de"] = datetime.now(tz=timezone.utc)

    @contextmanager
    def _fake_db_connection():
        yield conn

    monkeypatch.setattr(cron_module, "config", cfg)
    monkeypatch.setattr(cron_module, "get_providers", lambda: {"energycharts_de": provider})
    monkeypatch.setattr(cron_module, "db_connection", _fake_db_connection)

    cron_module.run_cron()

    assert provider.current_calls == 0
    assert provider.historical_calls == 0
    assert provider.future_calls == 0
    assert conn.commits == 0


def test_run_cron_runs_source_if_update_iterval_elapsed(monkeypatch) -> None:
    provider = _CountingProvider()
    cfg = _make_config(Source(region="DE", provider="energycharts", update_iterval=15))
    conn = _FakeConnection()
    previous_run = datetime.now(tz=timezone.utc) - timedelta(seconds=16)
    conn.last_runs["energycharts_de"] = previous_run

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
    assert conn.last_runs["energycharts_de"] > previous_run


def test_run_cron_force_run_bypasses_update_iterval(monkeypatch) -> None:
    provider = _CountingProvider()
    cfg = _make_config(Source(region="DE", provider="energycharts", update_iterval=30))
    conn = _FakeConnection()
    conn.last_runs["energycharts_de"] = datetime.now(tz=timezone.utc)

    @contextmanager
    def _fake_db_connection():
        yield conn

    monkeypatch.setattr(cron_module, "config", cfg)
    monkeypatch.setattr(cron_module, "get_providers", lambda: {"energycharts_de": provider})
    monkeypatch.setattr(cron_module, "db_connection", _fake_db_connection)

    cron_module.run_cron(specific_region="DE")

    assert provider.current_calls == 0
    assert provider.historical_calls == 1
    assert provider.future_calls == 1
    assert conn.commits == 1
