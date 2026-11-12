import requests
from datetime import datetime, timezone
from typing import Optional

from elephant.providers.emission_factors import EMISSION_FACTORS

BASE ="https://www.smard.de/app/chart_data"

# SMARD filters with their factors. Storage (4070 Pumpspeicher) is left out, see emission_factors.py.
filters = {
    # Braunkohle
    "1223": EMISSION_FACTORS["lignite"],

    # Kernenergie
    #"1224": EMISSION_FACTORS["nuclear"],

    # Wind Offshore
    "1225": EMISSION_FACTORS["wind_offshore"],

    # Wasserkraft
    "1226": EMISSION_FACTORS["hydro"],

    # Sonstige Konventionelle
    # SMARD: Abgeleitetes Gas aus Kohle, Mineralöl, Abfall, Gichtgas, Hochofengas, Raffineriegas,
    # Gas mit hohem Wasserstoffanteil, sonstige Reststoffe. [SMARD FAQ]
    "1227": EMISSION_FACTORS["other_conventional"],

    # Sonstige Erneuerbare
    # SMARD: Erdwärme, Deponiegas, Klärgas, Grubengas. [SMARD FAQ]
    # The factor covers Klär- and Deponiegas. Geothermie and Grubengas are small in volume; we neglect them in the average.
    "1228": EMISSION_FACTORS["other_renewable"],

    # Biomasse
    "4066": EMISSION_FACTORS["biomass"],

    # Wind Onshore
    "4067": EMISSION_FACTORS["wind_onshore"],

    # Photovoltaik
    "4068": EMISSION_FACTORS["solar"],

    # Steinkohle
    "4069": EMISSION_FACTORS["hard_coal"],

    # Erdgas
    "4071": EMISSION_FACTORS["natural_gas"],
}

LOAD_FILTER = 410

# SMARD publishes weekly chunks starting Monday 00:00. Two chunks always cover at least the last 7 days, so late
# corrections get re-fetched.
RECENT_CHUNKS = 2

def fetch_json(url: str) -> Optional[dict]:
    try:
        response = requests.get(url, timeout=5.0)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return None


def get_latest_timestamp(smard_filter, region= "DE", res= "quarterhour") -> Optional[int]:

    idx = fetch_json(f"{BASE}/{smard_filter}/{region}/index_{res}.json")
    if not idx:
        return None

    timestamps = idx.get("timestamps", None)

    if not timestamps:
        return None

    return timestamps

def get_series(smard_filter, timestamp, region= "DE", res= "quarterhour") -> Optional[dict]:
    data = fetch_json(f"{BASE}/{smard_filter}/{region}/{smard_filter}_{region}_{res}_{timestamp}.json")

    if not data:
        return None

    load_series = dict(data.get("series"))
    load_series = {t_ms: val for t_ms, val in load_series.items() if val is not None}

    return load_series


def get_co2intensity(region: str, resolution: str, scan_all: bool = False) -> Optional[tuple[dict[int, float], dict[int, tuple[float, float]]]]:

    # We need to get the timestamps that we can get data for
    time_stamps = get_latest_timestamp(LOAD_FILTER, region, resolution)

    if time_stamps is None:
        return None

    if not scan_all:
        time_stamps = sorted(time_stamps)[-RECENT_CHUNKS:]

    ci = {}  # timestamp_ms → gCO2eq/kWh

    for ts in time_stamps:
        load_series = get_series(LOAD_FILTER, ts, region, resolution)


        if not load_series:
            return None

        # Build a cache of all the different generation methods with the same timestamp
        generation_series: dict[str, dict[int, float]] = {}

        for f_id in filters:
            gen_series = get_series(f_id, ts, region, resolution)

            # Skipping a production type would compute the intensity without it, so a failed fetch fails the round
            if gen_series is None:
                return None

            generation_series[f_id] = dict(gen_series)

        for t_ms, _ in load_series.items():
            num = 0.0
            sum_load = 0.0

            abort = False

            for f_id, factor in filters.items():

                gen_series = generation_series.get(f_id, None)
                if gen_series is None:
                    continue

                gen_mw = gen_series.get(t_ms, None)
                if gen_mw is None:
                    gen_series = get_series(f_id, ts, region, resolution)
                    if gen_series is None:
                        return None
                    generation_series[f_id] = gen_series
                    gen_mw = gen_series.get(t_ms, None)

                # Some providers don't update as fast as the main times. In this case we abort and wait for this data to be available
                if gen_mw is None:
                    abort = True
                    break

                num += gen_mw * factor
                sum_load += gen_mw

            if abort:
                break

            ci[datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc)] = num / sum_load # So we get it in gCO2eq/kWh

    return ci


if __name__ == "__main__":
    result = get_co2intensity("DE", "quarterhour", scan_all=False)
    if result is None:
        print("Failed to fetch data from SMARD.")
    else:
        for i, j in result.items():
            dt = i.astimezone().isoformat()
            print(f"{dt}: {j} gCO2eq/kWh")
