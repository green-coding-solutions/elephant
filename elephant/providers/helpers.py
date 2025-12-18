
import logging

from .base import CarbonIntensityProvider
from .electricitymaps import ElectricityMapsProvider
from .bundesnetzagentur import BundesnetzagenturProvider
from .bundesnetzagentur_all import BundesnetzagenturProvider as BundesnetzagenturAllProvider
from ..config import config

logging.basicConfig(level=config.logging.level)
logger = logging.getLogger(__name__)


def get_providers() -> dict[str, CarbonIntensityProvider]:
    """Initialize and return the configured providers."""

    providers: dict[str, CarbonIntensityProvider] = {}

    if config.providers.get("electricitymaps") and config.providers["electricitymaps"].enabled:
        providers["electricitymaps"] = ElectricityMapsProvider(config.providers["electricitymaps"])
        logger.debug("ElectricityMaps provider initialized")

    if config.providers.get("bundesnetzagentur") and config.providers["bundesnetzagentur"].enabled:
        providers["bundesnetzagentur"] = BundesnetzagenturProvider(config.providers["bundesnetzagentur"])
        logger.debug("Bundesnetzagentur provider initialized")

    if config.providers.get("bundesnetzagentur_all") and config.providers["bundesnetzagentur_all"].enabled:
        providers["bundesnetzagentur_all"] = BundesnetzagenturAllProvider(config.providers["bundesnetzagentur_all"])
        logger.debug("Bundesnetzagentur all provider initialized")


    return providers
