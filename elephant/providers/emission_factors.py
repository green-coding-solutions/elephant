"""Shared lifecycle emission factors for providers that derive carbon intensity from the generation mix.

All values are gCO2eq per kWh of electricity. Links to the sources are in API_SOURCES.md.

Storage (pumped hydro, batteries) has no factor on purpose. It releases energy that was already generated, so counting
its discharge would count that energy twice.
"""

EMISSION_FACTORS = {
    # --- Umweltbundesamt (UBA): Emissionsbilanz erneuerbarer Energieträger 2023 ---
    #
    # Tabelle 6 lists these per kWh of primary energy (footnote 26), so they are divided by the mean Brutto-Nutzungsgrad
    # from Tabelle 5 (both on page 50). Page 49 says to multiply, but only dividing fits the report's own results.
    "lignite": 409.03 / 0.398,
    "hard_coal": 382.51 / 0.437,
    "natural_gas": 256.32 / 0.56,
    "oil": 312.70 / 0.377,  # Heizöl leicht
    "nuclear": 18.27 / 0.33,  # Fuel chain of German power generation
    #
    # Already per kWh of electricity, as the Brutto-Nutzungsgrad is set to 100 percent
    "solar": 56.51,  # Page 53, Tabelle 9
    "wind_onshore": 17.61,  # Page 57, Tabelle 13
    "wind_offshore": 9.62,  # Page 60, Tabelle 17
    "hydro_run_of_river": 2.66,  # Page 62, Tabelle 21
    "hydro_reservoir": 23.82,  # Page 62, Tabelle 21 (Speicherwasser with natural inflow)
    "geothermal": 149.35,  # Page 65, Tabelle 26
    #
    # Caused emissions in t CO2-Äq. divided by generation in GWh
    "hydro": 82_215 / 19_894,  # All hydro, for sources that don't split it. Tabelle 19, 22
    "biomass": (
        638_595  # Feste Biomasse, 9,996 GWh. Tabelle 28, 32. Biogenic CO2 from burning wood is not counted (Abbildung 17)
        + 8_041_194  # Biogas, 28,387 GWh. Tabelle 33, 37
        + 816_472  # Biomethan, 3,120 GWh. Tabelle 33, 38
        + 70_405  # Flüssige Biomasse, 105 GWh. Tabelle 39, 43
    ) / (9_996 + 28_387 + 3_120 + 105),
    "other_renewable": (
        160_209  # Klärgas, 1,529 GWh. Tabelle 44, 48
        + 25_309  # Deponiegas, 187 GWh. Tabelle 49, 53
    ) / (1_529 + 187),
    #
    # --- IPCC AR5 WG3 Annex III (2014), Table A.III.2, lifecycle median ---
    #
    # UBA has no value. AR6 WG3 Chapter 6 (2022) has no per-technology table that replaces this one.
    "marine": 17,
}

# --- Types without a matching source value, which use the closest factor above ---
#
# SMARD's "Sonstige Konventionelle" and ENTSO-E's "Fossil Coal-derived gas" and "Other" are mixed or unknown fuels.
EMISSION_FACTORS["other_conventional"] = EMISSION_FACTORS["oil"]
EMISSION_FACTORS["coal_derived_gas"] = EMISSION_FACTORS["other_conventional"]
# Low-grade solid fuels, for which we use the closest UBA fuel
EMISSION_FACTORS["peat"] = EMISSION_FACTORS["lignite"]
EMISSION_FACTORS["oil_shale"] = EMISSION_FACTORS["lignite"]
# Electricity Maps maps waste to biomass. UBA only covers the biogenic share of waste (Tabelle 56), which is too low
# for all waste as it excludes the fossil share.
EMISSION_FACTORS["waste"] = EMISSION_FACTORS["biomass"]
