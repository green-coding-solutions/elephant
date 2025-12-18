"""Main FastAPI application for Elephant service."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Any, AsyncGenerator, Dict, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, HTMLResponse
from psycopg import Connection

from elephant.config import load_config, Config
from elephant.database import connection_dependency, fetch_between, fetch_latest, fetch_regions
from elephant.cron import run_cron
from elephant.providers.helpers import get_providers



logger = logging.getLogger(__name__)
INDEX_HTML = (Path(__file__).resolve().parent / "templates" / "index.html").read_text(encoding="utf-8")

# Global configuration and providers
config: Optional[Config] = None


def _get_primary_source(region: str) -> str:
    """Return the configured primary provider name for a region (from cron sources)."""

    if not config:
        raise HTTPException(status_code=500, detail="Configuration not loaded")

    region_upper = region.upper()

    primary_sources = [
        source.provider
        for source in config.cron.sources
        if source.region.upper() == region_upper and getattr(source, "primary", False)
    ]

    if not primary_sources:
        raise HTTPException(status_code=400, detail=f"No primary provider configured for region '{region_upper}'")
    if len(primary_sources) > 1:
        logger.warning("Multiple primary providers configured for %s; using '%s'", region_upper, primary_sources[0])

    return primary_sources[0].lower()


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

        logger.info("Application startup complete")
        yield

    except Exception as e:
        logger.error("Failed to start application: %s", e)
        raise

    finally:
        logger.info("Application shutdown complete")


app = FastAPI(
    title="Elephant Carbon Grid Intensity Service",
    description="Specialized Carbon Grid Intensity (CGI) service",
    version="0.1",
    lifespan=lifespan,
)


@app.exception_handler(ValueError)
async def value_error_handler(_: Any, exc: ValueError) -> JSONResponse:
    """Handle configuration validation errors."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve a simple dashboard for viewing carbon intensity data."""
    return HTMLResponse(INDEX_HTML)



@app.get("/regions")
async def list_regions(db: Connection = Depends(connection_dependency)) -> list[str]:
    """Return all regions with stored data."""
    return fetch_regions(db)


@app.get("/carbon-intensity/current")
async def get_current_carbon_intensity(
    region: str = Query(..., description="Country code (e.g., 'DE', 'US', 'FR')"),
    update: bool = Query(False, description="If true, fetch fresh data before returning results"),
    db: Connection = Depends(connection_dependency)) -> Dict[str, Any]:
    """Get current carbon grid intensity for a region."""
    if not region:
        raise HTTPException(status_code=400, detail="region parameter is required")

    # Validate region format (ISO 3166-1 alpha-2)
    if len(region) != 2 or not region.isalpha():
        raise HTTPException(
            status_code=400, detail="region must be a valid ISO 3166-1 alpha-2 country code (e.g., 'DE', 'US')"
    )

    region = region.upper()

    if update:
        await run_in_threadpool(run_cron, region=region)

    # Query the database for the most recent entry
    results = fetch_latest(db, region)

    if results:
        return results

    raise HTTPException(
        status_code=404,
        detail="No carbon intensity data available for this region. Please check back later.",
    )


@app.get("/carbon-intensity/current/primary")
async def get_primary_carbon_intensity(
    region: str = Query(..., description="Country code (e.g., 'DE', 'US', 'FR')"),
    update: bool = Query(False, description="If true, fetch fresh data before returning results"),
    db: Connection = Depends(connection_dependency),
) -> Dict[str, Any]:
    """Get current carbon grid intensity for the configured primary provider for the region."""


    results = await get_current_carbon_intensity(region=region, update=update, db=db)

    primary_source = _get_primary_source(region)

    matched_key = next(
        (
            key
            for key in results.keys()
            if key.lower() == primary_source or key.lower().startswith(f"{primary_source}_")
        ),
        None,
    )

    if not matched_key:
        raise HTTPException(
            status_code=404,
            detail=f"No carbon intensity data available for primary provider '{primary_source}' in this region.",
        )

    return {matched_key: results[matched_key]}


@app.get("/carbon-intensity/history")
async def get_carbon_intensity_history(
    region: str = Query(..., description="Country code (e.g., 'DE', 'US', 'FR')"),
    startTime: str = Query(..., description="Start time in ISO 8601 format (e.g., '2025-09-22T10:00:00Z')"),
    endTime: str = Query(..., description="End time in ISO 8601 format (e.g., '2025-09-22T12:00:00Z')"),
    db: Connection = Depends(connection_dependency)
) -> List[dict]:
    """Get historical carbon grid intensity for a region and time range."""
    if not region:
        raise HTTPException(status_code=400, detail="region parameter is required")

    if not startTime:
        raise HTTPException(status_code=400, detail="startTime parameter is required")

    if not endTime:
        raise HTTPException(status_code=400, detail="endTime parameter is required")

    # Validate region format (ISO 3166-1 alpha-2)
    if len(region) != 2 or not region.isalpha():
        raise HTTPException(
            status_code=400, detail="region must be a valid ISO 3166-1 alpha-2 country code (e.g., 'DE', 'US')"
        )

    region = region.upper()

    # Parse datetime strings
    try:
        start_dt = datetime.fromisoformat(startTime.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(endTime.replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid datetime format. Use ISO 8601 format (e.g., '2025-09-22T10:00:00Z'): {str(e)}",
        ) from e

    # Validate time range
    if start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="startTime must be before endTime")

    # Query the database
    results = fetch_between(db, region, start_dt, end_dt)

    return results or []


#pylint: disable=broad-exception-caught
@app.get("/health")
async def health_check(db: Connection = Depends(connection_dependency)) -> dict:
    """Health check endpoint."""
    providers = list(get_providers().keys())

    record_count = None
    try:
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM carbon;")
            row = cur.fetchone()
            record_count = row[0] if row else 0
    except Exception as exc:
        logger.warning("Health check database count failed: %s", exc)
        return {"status": "error", "details": "database query failed"}

    return {"status": "healthy", "providers": providers, "db_records": record_count, "regions": fetch_regions(db)}
