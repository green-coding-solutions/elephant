
import logging
from typing import Callable

from .base import CarbonIntensityProvider
from .electricitymaps import ElectricityMapsProvider
from .bundesnetzagentur import BundesnetzagenturProvider
from .bundesnetzagentur_all import BundesnetzagenturProvider as BundesnetzagenturAllProvider
from .energycharts import EnergyChartsProvider
from ..config import ProviderConfig, config

logging.basicConfig(level=config.logging.level)
logger = logging.getLogger(__name__)

_PROVIDER_FACTORIES: dict[str, Callable[[ProviderConfig], CarbonIntensityProvider]] = {
    "electricitymaps": ElectricityMapsProvider,
    "energycharts": EnergyChartsProvider,
    "bundesnetzagentur": BundesnetzagenturProvider,
    "bundesnetzagentur_all": BundesnetzagenturAllProvider,
}


def get_providers() -> dict[str, CarbonIntensityProvider]:
    """Initialize and return the providers referenced by cron sources."""

    providers: dict[str, CarbonIntensityProvider] = {}
    seen: set[str] = set()

    for source in config.cron.sources:
        provider_name = source.provider.lower()
        provider_name_reg = f"{source.provider.lower()}_{source.region.lower()}"

        if provider_name_reg in seen:
            continue

        factory = _PROVIDER_FACTORIES.get(provider_name, None)

        if not factory:
            raise ValueError(f"Provider '{provider_name}' referenced in cron but no implementation is available.")

        provider_config = config.providers.get(provider_name, ProviderConfig())
        providers[provider_name_reg] = factory(provider_config)
        seen.add(provider_name_reg)
        logger.debug("%s provider initialized", provider_name_reg)

    return providers
