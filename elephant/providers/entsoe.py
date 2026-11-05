"""ENTSO-E Transparency Platform provider for carbon intensity data.

ENTSO-E publishes generation in MW per production type, not carbon intensity. We derive it as the
generation-weighted mean of lifecycle emission factors. This describes what a region generates: imports and exports
are not considered.

API docs: https://transparencyplatform.zendesk.com/hc/en-us/articles/15692855254548
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import List

import requests
from fastapi import HTTPException
from requests import RequestException

from elephant.config import ProviderConfig

from .base import CarbonIntensityProvider


logger = logging.getLogger(__name__)

BASE_URL = "https://web-api.tp.entsoe.eu/api"
PROVIDER_NAME = "entsoe"
HISTORY_WINDOW = timedelta(hours=24)
REQUEST_TIMEOUT_SECONDS = 30

# https://transparencyplatform.zendesk.com/hc/en-us/articles/15885757676308
AREA_CODES = {
    "DE": "10Y1001A1001A83F",
    "ES": "10YES-REE------0",
    "FR": "10YFR-RTE------C",
}

# Lifecycle gCO2eq/kWh per production type, using the values and the type mapping of Electricity Maps:
# https://github.com/electricitymaps/electricitymaps-contrib/blob/master/config/defaults.yaml
# https://github.com/electricitymaps/electricitymaps-contrib/blob/master/electricitymap/contrib/parsers/ENTSOE.py
#
# Storage (B10 pumped hydro, B25 energy storage) is left out on purpose. It releases energy that was already
# generated, so counting its discharge would count that energy twice.
EMISSION_FACTORS = {
    "B01": 230,  # Biomass
    "B02": 820,  # Fossil Brown coal/Lignite
    "B03": 490,  # Fossil Coal-derived gas
    "B04": 490,  # Fossil Gas
    "B05": 820,  # Fossil Hard coal
    "B06": 650,  # Fossil Oil
    "B07": 820,  # Fossil Oil shale
    "B08": 820,  # Fossil Peat
    "B09": 38,   # Geothermal
    "B11": 24,   # Hydro Run-of-river and pondage
    "B12": 24,   # Hydro Water Reservoir
    "B13": 700,  # Marine (unknown)
    "B14": 12,   # Nuclear
    "B15": 700,  # Other renewable (unknown)
    "B16": 45,   # Solar
    "B17": 230,  # Waste
    "B18": 11,   # Wind Offshore
    "B19": 11,   # Wind Onshore
    "B20": 700,  # Other (unknown)
}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_resolution(value: str) -> timedelta:
    match = re.fullmatch(r"PT([1-9]\d*)M", value)
    if not match:
        raise ValueError(f"Unsupported resolution '{value}'")
    return timedelta(minutes=int(match.group(1)))


def _parse_generation(xml_text: str) -> tuple[dict[datetime, dict[str, float]], timedelta | None]:
    """Return the MW per production type for each timestamp, and the finest resolution in the response."""
    root = ET.fromstring(xml_text)

    # ENTSO-E answers HTTP 200 with an acknowledgement document when there is no matching data
    if root.tag.endswith("Acknowledgement_MarketDocument"):
        logger.warning("ENTSO-E returned no data: %s", root.findtext("{*}Reason/{*}text"))
        return {}, None

    # Production types can report at different resolutions, so everything is expanded onto the finest one
    finest = min((_parse_resolution(res.text) for res in root.findall(".//{*}resolution")), default=None)
    generation: dict[datetime, dict[str, float]] = {}

    for series in root.findall("{*}TimeSeries"):
        psr_type = series.findtext("{*}MktPSRType/{*}psrType")

        # Series with outBiddingZone_Domain hold consumption, for example pumping water uphill
        if series.find("{*}inBiddingZone_Domain.mRID") is None or psr_type not in EMISSION_FACTORS:
            continue

        # A03 leaves out positions whose value did not change. In A01 a left out position is a missing value.
        repeat_last_value = series.findtext("{*}curveType") != "A01"

        for period in series.findall("{*}Period"):
            start = _parse_time(period.findtext("{*}timeInterval/{*}start"))
            end = _parse_time(period.findtext("{*}timeInterval/{*}end"))
            step = _parse_resolution(period.findtext("{*}resolution"))
            points = {
                int(point.findtext("{*}position")): float(point.findtext("{*}quantity"))
                for point in period.findall("{*}Point")
            }

            value = None
            for offset in range((end - start) // finest):
                position = offset * finest // step + 1
                value = points.get(position, value if repeat_last_value else None)
                if value is not None:
                    generation.setdefault(start + offset * finest, {})[psr_type] = value

    return generation, finest


class EntsoeProvider(CarbonIntensityProvider):
    """Provider that derives carbon intensity from ENTSO-E generation per production type."""

    def __init__(self, config: ProviderConfig):
        self.config = config
        if not config.api_token:
            raise ValueError("API token is required for EntsoeProvider.")

    def _get(self, region: str, start_time: datetime, end_time: datetime) -> str:
        """Fetch Actual Generation per Production Type [16.1.B&C] as XML."""
        area_code = AREA_CODES.get(region.upper())
        if not area_code:
            raise HTTPException(status_code=400, detail=f"ENTSO-E area code for region '{region}' is not configured")

        try:
            response = requests.get(
                BASE_URL,
                params={
                    "documentType": "A75",
                    "processType": "A16",
                    "in_Domain": area_code,
                    "periodStart": start_time.astimezone(timezone.utc).strftime("%Y%m%d%H%M"),
                    "periodEnd": end_time.astimezone(timezone.utc).strftime("%Y%m%d%H%M"),
                    "securityToken": self.config.api_token,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.text
        except RequestException as exc:
            # The exception text contains the URL and with it the security token, so it must not be logged or chained
            status = exc.response.status_code if exc.response is not None else type(exc).__name__
            logger.error("ENTSO-E request for region '%s' failed: %s", region, status)
            raise HTTPException(status_code=503, detail="ENTSO-E service temporarily unavailable") from None

    def get_current(self, region: str) -> List[dict]:
        """Get the most recent carbon intensity for which all production types have reported."""
        return self.get_historical(region)[-1:]

    def get_historical(self, region: str, start_time: datetime = None, end_time: datetime = None) -> List[dict]:
        """Get historical carbon intensity data for a region and time range, ordered by time."""
        end_time = end_time or datetime.now(tz=timezone.utc)
        start_time = start_time or end_time - HISTORY_WINDOW

        xml_text = self._get(region, start_time, end_time)

        # Anything but an HTTPException would stop the cron process
        try:
            generation, finest = _parse_generation(xml_text)
        except (ET.ParseError, ValueError, TypeError, AttributeError) as exc:
            logger.error("Could not parse ENTSO-E response for region '%s': %s", region, exc)
            raise HTTPException(status_code=502, detail="ENTSO-E returned an unexpected response") from exc

        # Production types publish with different delays. Without a late type the result would be badly skewed, for
        # example France without nuclear, so we only use timestamps for which all types have reported.
        reporting_types = {psr_type for mix in generation.values() for psr_type in mix}

        entries = []
        for time, mix in sorted(generation.items()):
            total_mw = sum(mix.values())
            if time >= end_time or mix.keys() != reporting_types or total_mw <= 0:
                continue

            entries.append(
                {
                    "region": region,
                    "time": time,
                    "carbon_intensity": sum(mw * EMISSION_FACTORS[psr] for psr, mw in mix.items()) / total_mw,
                    "provider": PROVIDER_NAME,
                    "resolution": self.config.resolution or f"{int(finest.total_seconds() // 60)}_minutes",
                    "estimation": False,
                }
            )

        if generation and not entries:
            logger.warning("ENTSO-E has no timestamp with all production types for region '%s'.", region)

        return entries

    def get_future(self, region: str) -> List[dict]:
        """ENTSO-E only forecasts wind, solar and totals, which does not give us a full generation mix."""
        return []
