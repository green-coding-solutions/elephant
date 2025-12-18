import requests
from datetime import datetime, timezone
from typing import Optional

BASE = "https://www.smard.de/app/chart_data"

# All Numbers from https://www.umweltbundesamt.de/sites/default/files/medien/11850/publikationen/03_2025_cc_emissionsbilanz_erneuerbarer_energien_2023.pdf
filters = {
    # Braunkohle 
    "1223": 409.03,  # Page 50, Tabelle 6

    # Kernenergie 
    #"1224": 18.27 ,    # Page 50, Tabelle 6

    # Wind Offshore
    "1225": 9.62 ,    # Page 60

    # Wasserkraft
    "1226": 2.66 ,   # Page 62

    # Sonstige Konventionelle
    # SMARD: Abgeleitetes Gas aus Kohle, Mineralöl, Abfall, Gichtgas, Hochofengas, Raffineriegas,
    # Gas mit hohem Wasserstoffanteil, sonstige Reststoffe. [SMARD FAQ]
    "1227": 312.70 ,   # Sonstige Konventionelle (approx., based on Heizöl + heavy fossil mix)

    # Sonstige Erneuerbare
    # SMARD: Erdwärme, Deponiegas, Klärgas, Grubengas. [SMARD FAQ]
    # UBA provides explicit data for Klärgas and Deponiegas (Sections 4.9 and 4.10):
    #   Klärgas: generation 1,529 GWh (Table 44), caused CO2-Äq. 160,209 t (Table 48).
    #   Deponiegas: generation 187 GWh (Table 49), caused CO2-Äq. 25,309 t (Table 53).
    # Combined factor = 185,518 t / 1,716 GWh ≈ 108.1 g/kWh.
    # Geothermie and Grubengas are small in volume; we neglect them in the average.
    "1228": 108.1,   # Sonstige Erneuerbare (Klär- + Deponiegas mix; approx., excludes Erdwärme/Grubengas)

    # Biomasse
    "4066": 125.96,   # Biomasse (142,96 + 108,96)/2 Page 81

    # Wind Onshore
    "4067": 17.61,    # Page 57

    # Photovoltaik
    "4068": 56.51 ,    # Page 53

    # Steinkohle
    "4069": 382.51 ,   # Page 50

    # Pumpspeicher
    "4070": 23.82,     # Page 62

    # Erdgas
    "4071": 256.32 ,   # Page 50
}

LOAD_FILTER = 410

def fetch_json(url: str) -> Optional[dict]:
    try:
        response = requests.get(url, timeout=30.0)
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


def get_co2intensity(region: str, resolution: str, all: bool = False) -> Optional[tuple[dict[int, float], dict[int, tuple[float, float]]]]:

    # We need to get the timestamps that we can get data for
    time_stamps = get_latest_timestamp(LOAD_FILTER, region, resolution)

    if time_stamps is None:
        return None

    if not all:
        time_stamps = [max(time_stamps)]

    ci = {}  # timestamp_ms → gCO2eq/kWh

    for ts in time_stamps:
        print("Geeting data for timestamp:", ts)
    
        load_series = get_series(LOAD_FILTER, ts, region, resolution)
                
        if not load_series:
            return None
        
        # Build a cache of all the different generation methods with the same timestamp 
        generation_series: dict[str, dict[int, float]] = {}

        for f_id in filters:
            gen_series = get_series(f_id, ts, region, resolution)
            if gen_series is None:
                return None
            
            generation_series[f_id] = dict(gen_series)

        for t_ms, _ in load_series.items():
            num = 0.0
            sum_load = 0.0

            abort = False

            for f_id, factor in filters.items():

                gen_series = generation_series[f_id]
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
    result = get_co2intensity("DE", "quarterhour", all=False)
    if result is None:
        print("Failed to fetch data from SMARD.")
    else:
        for i, j in result.items():
            dt = i.astimezone().isoformat()
            print(f"{dt}: {j} gCO2eq/kWh")
