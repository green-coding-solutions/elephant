"""Tests for the shared emission factor table and the providers using it."""

import pytest

from elephant.providers.bna_helper import filters
from elephant.providers.emission_factors import EMISSION_FACTORS
from elephant.providers.entsoe import PSR_TYPES


@pytest.mark.parametrize(
    ("fuel", "expected"),
    [
        ("lignite", 1027.7),
        ("hard_coal", 875.3),
        ("natural_gas", 457.7),
        ("oil", 829.4),
        ("nuclear", 55.4),
        ("biomass", 229.9),
        ("hydro", 4.13),
        ("hydro_run_of_river", 2.66),
        ("hydro_reservoir", 23.82),
        ("geothermal", 149.35),
        ("other_renewable", 108.1),
        ("marine", 17),
    ],
)
def test_values_are_per_kwh_of_electricity(fuel, expected) -> None:
    assert EMISSION_FACTORS[fuel] == pytest.approx(expected, abs=0.1)


def test_every_entsoe_type_has_a_factor() -> None:
    assert set(PSR_TYPES.values()) <= set(EMISSION_FACTORS)


@pytest.mark.parametrize(
    ("psr_type", "smard_filter"),
    [
        ("B01", "4066"),
        ("B02", "1223"),
        ("B04", "4071"),
        ("B05", "4069"),
        ("B15", "1228"),
        ("B16", "4068"),
        ("B18", "1225"),
        ("B19", "4067"),
        ("B20", "1227"),
    ],
)
def test_both_providers_use_the_same_factor_for_the_same_type(psr_type, smard_filter) -> None:
    assert EMISSION_FACTORS[PSR_TYPES[psr_type]] == filters[smard_filter]


def test_storage_has_no_factor() -> None:
    assert "B10" not in PSR_TYPES
    assert "B25" not in PSR_TYPES
    assert "4070" not in filters
