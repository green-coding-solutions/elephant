"""Main FastAPI application for Elephant service."""

import logging
from contextlib import asynccontextmanager
from typing import Optional, Any, AsyncGenerator, Dict

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from .config import load_config, Config
from .models import CarbonIntensityResponse
from .providers.base import CarbonIntensityProvider
from .providers.electricitymaps import ElectricityMapsProvider
from . import __version__


logger = logging.getLogger(__name__)

# Global configuration and providers
config: Optional[Config] = None
carbon_providers: Dict[str, CarbonIntensityProvider] = {}


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    global config  # pylint: disable=global-statement

    try:
        config = load_config()

        # Configure logging
        log_level = config.logging.level.upper()  # pylint: disable=no-member
        logging.basicConfig(level=getattr(logging, log_level))
        logger.info("Starting %s", fastapi_app.title)

        # Initialize providers
        electricitymaps_config = config.providers.get("electricitymaps")  # pylint: disable=no-member
        if electricitymaps_config and electricitymaps_config.enabled:
            carbon_providers["electricitymaps"] = ElectricityMapsProvider(electricitymaps_config)
            logger.info("ElectricityMaps provider initialized")

        if not carbon_providers:
            logger.info("No external providers configured - simulation-only mode")

        logger.info("Application startup complete")
        yield

    except Exception as e:
        logger.error("Failed to start application: %s", e)
        raise

    finally:
        # Cleanup providers
        for provider in carbon_providers.values():
            close_method = getattr(provider, "close", None)
            if close_method and callable(close_method):
                await close_method()
        logger.info("Application shutdown complete")


app = FastAPI(
    title="Elephant Carbon Grid Intensity Service",
    description="Specialized dockerized Carbon Grid Intensity (CGI) service with simulation capabilities",
    version=__version__,
    lifespan=lifespan,
)


@app.exception_handler(ValueError)
async def value_error_handler(_: Any, exc: ValueError) -> JSONResponse:
    """Handle configuration validation errors."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/carbon-intensity/current", response_model=CarbonIntensityResponse)
async def get_current_carbon_intensity(
    location: str = Query(..., description="Country code (e.g., 'DE', 'US', 'FR')")
) -> CarbonIntensityResponse:
    """Get current carbon grid intensity for a location."""
    if not location:
        raise HTTPException(status_code=400, detail="Location parameter is required")

    # Validate location format (ISO 3166-1 alpha-2)
    if len(location) != 2 or not location.isalpha():
        raise HTTPException(
            status_code=400, detail="Location must be a valid ISO 3166-1 alpha-2 country code (e.g., 'DE', 'US')"
        )

    location = location.upper()

    # Try ElectricityMaps provider first
    if "electricitymaps" in carbon_providers:
        try:
            return await carbon_providers["electricitymaps"].get_current(location)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Unexpected error from ElectricityMaps provider: %s", e)
            raise HTTPException(status_code=503, detail="Carbon intensity service temporarily unavailable") from e

    raise HTTPException(
        status_code=503,
        detail="No carbon intensity providers available. Use simulation endpoints for testing scenarios.",
    )


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "providers": list(carbon_providers.keys())}
