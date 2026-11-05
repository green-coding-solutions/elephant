"""Tests for the ENTSO-E provider."""

import logging
from datetime import datetime, timezone

import pytest
import requests
from fastapi import HTTPException

from elephant.config import ProviderConfig
from elephant.providers import entsoe
from elephant.providers.entsoe import EntsoeProvider
from elephant.providers.helpers import _PROVIDER_FACTORIES

TOKEN = "secret-token"
START = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
END = datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc)
ROW_KEYS = {"region", "time", "carbon_intensity", "provider", "resolution", "estimation"}


def _series(psr_type, points, curve="A03", resolution="PT15M", direction="in", start="00:00", end="01:00") -> str:
    point_xml = "".join(f"<Point><position>{pos}</position><quantity>{qty}</quantity></Point>" for pos, qty in points)
    return f"""
    <TimeSeries>
      <{direction}BiddingZone_Domain.mRID codingScheme="A01">AREA</{direction}BiddingZone_Domain.mRID>
      <curveType>{curve}</curveType>
      <MktPSRType><psrType>{psr_type}</psrType></MktPSRType>
      <Period>
        <timeInterval><start>2024-01-01T{start}Z</start><end>2024-01-01T{end}Z</end></timeInterval>
        <resolution>{resolution}</resolution>
        {point_xml}
      </Period>
    </TimeSeries>"""


def _document(*series) -> str:
    return (
        '<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">'
        f'{"".join(series)}</GL_MarketDocument>'
    )


def _provider(monkeypatch, xml_text: str) -> EntsoeProvider:
    provider = EntsoeProvider(ProviderConfig(api_token=TOKEN))
    monkeypatch.setattr(provider, "_get", lambda region, start, end: xml_text)
    return provider


def _at(minute: int) -> datetime:
    return datetime(2024, 1, 1, 0, minute, tzinfo=timezone.utc)


def test_provider_is_registered() -> None:
    assert _PROVIDER_FACTORIES["entsoe"] is EntsoeProvider


def test_requires_api_token() -> None:
    with pytest.raises(ValueError, match="API token"):
        EntsoeProvider(ProviderConfig())


def test_intensity_is_generation_weighted_and_includes_nuclear(monkeypatch) -> None:
    xml_text = _document(
        _series("B14", [(1, 900)], resolution="PT60M"),
        _series("B04", [(1, 100)], resolution="PT60M"),
    )

    rows = _provider(monkeypatch, xml_text).get_historical("FR", START, END)

    assert len(rows) == 1
    assert set(rows[0]) == ROW_KEYS
    assert rows[0]["time"] == START
    assert rows[0]["region"] == "FR"
    assert rows[0]["resolution"] == "60_minutes"
    assert rows[0]["estimation"] is False
    assert rows[0]["carbon_intensity"] == pytest.approx((900 * 12 + 100 * 490) / 1000)


def test_consumption_and_storage_are_excluded(monkeypatch) -> None:
    xml_text = _document(
        _series("B19", [(1, 100)], resolution="PT60M"),
        _series("B04", [(1, 5000)], resolution="PT60M", direction="out"),
        _series("B10", [(1, 5000)], resolution="PT60M"),
        _series("B25", [(1, 5000)], resolution="PT60M"),
    )

    rows = _provider(monkeypatch, xml_text).get_historical("DE", START, END)

    assert [row["carbon_intensity"] for row in rows] == [pytest.approx(11)]


def test_a03_repeats_values_for_left_out_positions(monkeypatch) -> None:
    xml_text = _document(_series("B19", [(1, 100), (3, 300)]), _series("B04", [(1, 100)]))

    rows = _provider(monkeypatch, xml_text).get_historical("DE", START, END)

    assert [row["time"] for row in rows] == [_at(0), _at(15), _at(30), _at(45)]
    expected_low = (100 * 11 + 100 * 490) / 200
    expected_high = (300 * 11 + 100 * 490) / 400
    assert [row["carbon_intensity"] for row in rows] == pytest.approx(
        [expected_low, expected_low, expected_high, expected_high]
    )


def test_a01_treats_left_out_positions_as_missing(monkeypatch) -> None:
    xml_text = _document(
        _series("B19", [(1, 100), (2, 100), (4, 100)], curve="A01"),
        _series("B04", [(1, 100), (2, 100), (3, 100), (4, 100)], curve="A01"),
    )

    rows = _provider(monkeypatch, xml_text).get_historical("DE", START, END)

    assert [row["time"] for row in rows] == [_at(0), _at(15), _at(45)]


def test_timestamps_with_a_late_production_type_are_skipped(monkeypatch) -> None:
    xml_text = _document(
        _series("B14", [(1, 900)], end="00:30"),
        _series("B04", [(1, 100)]),
    )
    provider = _provider(monkeypatch, xml_text)

    rows = provider.get_historical("FR", START, END)

    assert [row["time"] for row in rows] == [_at(0), _at(15)]
    assert provider.get_current("FR")[0]["time"] == _at(15)


def test_mixed_resolutions_are_expanded_to_the_finest(monkeypatch) -> None:
    xml_text = _document(
        _series("B14", [(1, 900)], resolution="PT60M"),
        _series("B04", [(1, 100)]),
    )

    rows = _provider(monkeypatch, xml_text).get_historical("FR", START, END)

    assert len(rows) == 4
    assert rows[0]["resolution"] == "15_minutes"


def test_timestamps_at_or_after_end_time_are_dropped(monkeypatch) -> None:
    rows = _provider(monkeypatch, _document(_series("B19", [(1, 100)]))).get_historical("DE", START, _at(30))

    assert [row["time"] for row in rows] == [_at(0), _at(15)]


def test_zero_generation_is_skipped(monkeypatch) -> None:
    rows = _provider(monkeypatch, _document(_series("B19", [(1, 0)]))).get_historical("DE", START, END)

    assert not rows


def test_no_matching_data_returns_nothing(monkeypatch) -> None:
    xml_text = (
        '<Acknowledgement_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:7:0">'
        "<Reason><code>999</code><text>No matching data found</text></Reason>"
        "</Acknowledgement_MarketDocument>"
    )
    provider = _provider(monkeypatch, xml_text)

    assert not provider.get_historical("DE", START, END)
    assert not provider.get_current("DE")


@pytest.mark.parametrize("xml_text", ["not xml", _document(_series("B19", [(1, 100)], resolution="P1D"))])
def test_unexpected_responses_raise_http_exception(monkeypatch, xml_text) -> None:
    with pytest.raises(HTTPException) as exc:
        _provider(monkeypatch, xml_text).get_historical("DE", START, END)

    assert exc.value.status_code == 502


def test_future_is_empty() -> None:
    assert not EntsoeProvider(ProviderConfig(api_token=TOKEN)).get_future("DE")


@pytest.mark.parametrize(
    ("region", "area_code"),
    [("DE", "10Y1001A1001A83F"), ("FR", "10YFR-RTE------C"), ("es", "10YES-REE------0")],
)
def test_request_parameters(monkeypatch, region, area_code) -> None:
    captured = {}

    class _Response:
        text = _document()

        def raise_for_status(self) -> None:
            pass

    def fake_get(url, params, timeout):
        captured.update(url=url, params=params, timeout=timeout)
        return _Response()

    monkeypatch.setattr(entsoe.requests, "get", fake_get)

    EntsoeProvider(ProviderConfig(api_token=TOKEN)).get_historical(region, START, END)

    assert captured["url"] == "https://web-api.tp.entsoe.eu/api"
    assert captured["params"] == {
        "documentType": "A75",
        "processType": "A16",
        "in_Domain": area_code,
        "periodStart": "202401010000",
        "periodEnd": "202401010100",
        "securityToken": TOKEN,
    }


def test_unconfigured_region_raises_http_exception(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("no request should be sent")

    monkeypatch.setattr(entsoe.requests, "get", fail)

    with pytest.raises(HTTPException) as exc:
        EntsoeProvider(ProviderConfig(api_token=TOKEN)).get_current("XX")

    assert exc.value.status_code == 400


def test_request_failure_does_not_expose_the_token(monkeypatch, caplog) -> None:
    def fake_get(*_args, **_kwargs):
        raise requests.ConnectionError(f"Max retries exceeded with url: /api?securityToken={TOKEN}")

    monkeypatch.setattr(entsoe.requests, "get", fake_get)

    with caplog.at_level(logging.DEBUG), pytest.raises(HTTPException) as exc:
        EntsoeProvider(ProviderConfig(api_token=TOKEN)).get_current("DE")

    assert exc.value.status_code == 503
    assert exc.value.__cause__ is None
    assert exc.value.__suppress_context__ is True
    assert TOKEN not in str(exc.value.detail)
    assert TOKEN not in caplog.text
