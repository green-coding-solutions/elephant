"""Tests for database yearly fallback helpers."""

from datetime import datetime, timezone

from elephant import database as database_module
from elephant.yearly_dataset import YEARLY_PROVIDER


class _DummyCursor:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *_args, **_kwargs):
        return None

    def fetchall(self):
        return self._rows


class _DummyConnection:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self, *args, **kwargs):
        return _DummyCursor(self._rows)


def test_fetch_between_uses_yearly_fallback_when_live_query_is_empty(monkeypatch) -> None:
    """fetch_between delegates to yearly fallback when the timeseries table has no rows."""
    sentinel = [{"time": datetime(2021, 1, 1, tzinfo=timezone.utc), "carbon_intensity": 100}]
    monkeypatch.setattr(database_module, "_fetch_between_yearly", lambda *args, **kwargs: sentinel)

    result = database_module.fetch_between(
        _DummyConnection([]),
        "DE",
        datetime(2021, 1, 1, tzinfo=timezone.utc),
        datetime(2021, 1, 1, 1, tzinfo=timezone.utc),
    )

    assert result == sentinel


def test_fetch_latest_uses_yearly_fallback_when_live_query_is_empty(monkeypatch) -> None:
    """fetch_latest delegates to yearly fallback when the timeseries table has no rows."""
    sentinel = [{"provider": YEARLY_PROVIDER, "carbon_intensity": 123, "estimated": True}]
    monkeypatch.setattr(database_module, "_fetch_latest_yearly", lambda *args, **kwargs: sentinel)

    result = database_module.fetch_latest(_DummyConnection([]), "DE")

    assert result == sentinel


def test_fetch_between_yearly_expands_15_minute_rows_across_years(monkeypatch) -> None:
    """Yearly fallback generates graphable 15-minute rows using the value for each year."""
    monkeypatch.setattr(
        database_module,
        "_fetch_yearly_rows",
        lambda *args, **kwargs: [
            {"year": 2021, "carbon_intensity": 100.0, "provider": YEARLY_PROVIDER},
            {"year": 2022, "carbon_intensity": 200.0, "provider": YEARLY_PROVIDER},
        ],
    )

    result = database_module._fetch_between_yearly(
        conn=None,
        region="DE",
        start_time=datetime(2021, 12, 31, 23, 30, tzinfo=timezone.utc),
        end_time=datetime(2022, 1, 1, 0, 30, tzinfo=timezone.utc),
    )

    assert [row["time"] for row in result] == [
        datetime(2021, 12, 31, 23, 30, tzinfo=timezone.utc),
        datetime(2021, 12, 31, 23, 45, tzinfo=timezone.utc),
        datetime(2022, 1, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2022, 1, 1, 0, 15, tzinfo=timezone.utc),
        datetime(2022, 1, 1, 0, 30, tzinfo=timezone.utc),
    ]
    assert [row["carbon_intensity"] for row in result] == [100.0, 100.0, 200.0, 200.0, 200.0]
    assert all(row["provider"] == YEARLY_PROVIDER for row in result)
    assert all(row["estimated"] is True for row in result)
