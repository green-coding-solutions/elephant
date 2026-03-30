"""Helpers for the bundled yearly Electricity Maps dataset."""

import json
import re
from pathlib import Path


YEARLY_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
YEARLY_PROVIDER = "electricitymaps_yearly"
_YEAR_PATTERN = re.compile(r"yearly_(\d{4})\.js$")
_DATA_PATTERN = re.compile(r"export const data = (\{.*?\})\s*export const methodology =", re.DOTALL)


def extract_year_from_path(path: Path) -> int:
    """Extract the dataset year from a bundled file path."""
    match = _YEAR_PATTERN.search(path.name)
    if not match:
        raise ValueError(f"Could not determine year from file name: {path}")
    return int(match.group(1))


def load_yearly_file(path: Path) -> dict:
    """Load a yearly JS data file as a Python dictionary."""
    content = path.read_text(encoding="utf-8")
    match = _DATA_PATTERN.search(content)
    if not match:
        raise ValueError(f"Could not locate dataset payload in {path}")
    return json.loads(match.group(1))


def iter_yearly_dataset_records(data_dir: Path = YEARLY_DATA_DIR) -> list[dict]:
    """Returns yearly dataset rows ready for database insertion."""
    retList = []

    for path in sorted(data_dir.glob("yearly_*.js")):
        year = extract_year_from_path(path)
        payload = load_yearly_file(path)

        for region, values in payload.items():
            zone = values.get("zone", {})
            carbon_intensity = values.get("carbonIntensity", {}).get("value")
            if carbon_intensity is None:
                continue

            retList.append({
                "year": year,
                "region": region.upper(),
                "carbon_intensity": float(carbon_intensity),
                "provider": YEARLY_PROVIDER,
                "zone_name": zone.get("zoneName"),
                "country_name": zone.get("countryName"),
                "display_name": zone.get("displayName"),
            })
    return retList
