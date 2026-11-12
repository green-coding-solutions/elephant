"""Offline tests for the SMARD helper."""

from datetime import datetime, timezone

import pytest

from elephant.providers import bna_helper

WEEK_MS = 7 * 24 * 3600 * 1000
CHUNKS = [0, WEEK_MS, 2 * WEEK_MS]


def _fake_smard(monkeypatch, missing_filter=None) -> list:
    """Every filter reports 100 MW at the start of each chunk. Returns the list of fetched (filter, chunk) pairs."""
    fetched = []

    def fake_series(smard_filter, timestamp, region="DE", res="quarterhour"):
        fetched.append((str(smard_filter), timestamp))
        if str(smard_filter) == missing_filter:
            return None
        return {timestamp: 100.0}

    monkeypatch.setattr(bna_helper, "get_latest_timestamp", lambda *args, **kwargs: list(reversed(CHUNKS)))
    monkeypatch.setattr(bna_helper, "get_series", fake_series)
    return fetched


def _at(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def test_uses_the_two_most_recent_chunks(monkeypatch) -> None:
    fetched = _fake_smard(monkeypatch)

    result = bna_helper.get_co2intensity("DE", "quarterhour")

    assert set(result) == {_at(WEEK_MS), _at(2 * WEEK_MS)}
    assert {chunk for _, chunk in fetched} == {WEEK_MS, 2 * WEEK_MS}


def test_scan_all_uses_every_chunk(monkeypatch) -> None:
    _fake_smard(monkeypatch)

    result = bna_helper.get_co2intensity("DE", "quarterhour", scan_all=True)

    assert set(result) == {_at(chunk) for chunk in CHUNKS}


def test_intensity_is_generation_weighted(monkeypatch) -> None:
    _fake_smard(monkeypatch)

    result = bna_helper.get_co2intensity("DE", "quarterhour")

    expected = sum(bna_helper.filters.values()) / len(bna_helper.filters)
    assert result[_at(2 * WEEK_MS)] == pytest.approx(expected)


def test_failed_production_type_fails_the_round(monkeypatch) -> None:
    """A type that cannot be fetched must not be left out of the mix."""
    _fake_smard(monkeypatch, missing_filter="1223")

    assert bna_helper.get_co2intensity("DE", "quarterhour") is None
