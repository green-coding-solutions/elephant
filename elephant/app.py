"""Main FastAPI application for Elephant service."""

import inspect
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Optional, Any, AsyncGenerator, Dict, List
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from psycopg import Connection
from pydantic import BaseModel, Field, field_validator

from elephant.config import Config, config as app_config
from elephant.database import connection_dependency, fetch_between, fetch_latest, fetch_regions
from elephant.cron import run_cron
from elephant.providers.helpers import get_providers
from elephant.simulation import (
    SimulationExhaustedError,
    SimulationNotFoundError,
    SimulationValueInput,
    simulation_store,
)

logger = logging.getLogger(__name__)
INDEX_HTML = (Path(__file__).resolve().parent / "templates" / "index.html").read_text(encoding="utf-8")

# Global configuration and providers
config: Config = app_config

EMISSION_FACTOR_TYPE = "lifecycle"
TEMPORAL_GRANULARITY = "notimplemented"  # Placeholder until we support variable granularities


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

    return f"{primary_sources[0].lower()}_{region.lower()}"


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    try:
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

if config.cors.allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors.allow_origins,
        allow_credentials=config.cors.allow_credentials,
        allow_methods=config.cors.allow_methods,
        allow_headers=config.cors.allow_headers,
    )


class SimulationCreateRequest(BaseModel):
    """Payload for creating a new simulation."""

    carbon_values: List[SimulationValueInput] = Field(
        ...,
        min_length=1,
        description="Ordered grid intensity values to replay. Accepts floats or (value, calls) tuples.",
    )

    @field_validator("carbon_values")
    @classmethod
    def _validate_uniform_carbon_values(cls, values: List[SimulationValueInput]) -> List[SimulationValueInput]:
        def _is_pair(entry: SimulationValueInput) -> bool:
            return isinstance(entry, (list, tuple))

        if not values:
            return values

        has_pairs = any(_is_pair(entry) for entry in values)
        has_scalars = any(not _is_pair(entry) for entry in values)

        if has_pairs and has_scalars:
            raise ValueError("carbon_values must be all numbers or all (value, calls) pairs")

        if has_pairs:
            for entry in values:
                if len(entry) != 2:
                    raise ValueError("Each (value, calls) entry must have exactly 2 items")

        return values


@app.exception_handler(ValueError)
async def value_error_handler(_: Any, exc: ValueError) -> JSONResponse:
    """Handle configuration validation errors."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _normalize_region(region: Optional[str]) -> str:
    """Validate and normalize a region value."""
    if not region:
        raise HTTPException(status_code=400, detail="region parameter is required")

    if len(region) != 2 or not region.isalpha():
        raise HTTPException(
            status_code=400,
            detail="region must be a valid ISO 3166-1 alpha-2 country code (e.g., 'DE', 'US')",
        )

    return region.upper()


async def _handle_update(update: bool|str, region: str) -> None:
    """Handle update logic for endpoints."""

    if update:
        if update is True or (isinstance(update, str) and update.lower() == 'true'):
            logger.info("Updating carbon intensity data for region '%s'...", region)
            await run_in_threadpool(run_cron, specific_region=region)
        elif isinstance(update, str):
            logger.info("Updating carbon intensity data for region '%s' and provider '%s'...", region, update)
            await run_in_threadpool(run_cron, specific_region=region, specific_provider=update)



def _to_iso(dt: datetime) -> str:
    """Return an ISO string with a Z suffix for UTC datetimes."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_em_current(zone: str, carbon_intensity: float, timestamp: datetime | None = None) -> Dict[str, Any]:
    """Format a single carbon intensity record in Electricity Maps style."""
    ts = _to_iso(timestamp or datetime.now(timezone.utc))
    return {
        "zone": zone,
        "carbonIntensity": float(carbon_intensity),
        "datetime": ts,
        "updatedAt": ts,
        "emissionFactorType": EMISSION_FACTOR_TYPE,
        "isEstimated": False,
        "estimationMethod": None,
        "temporalGranularity": TEMPORAL_GRANULARITY,
    }


def _format_em_history_entry(record: dict) -> Dict[str, Any]:
    """Format a history entry for Electricity Maps style responses."""
    ts = _to_iso(record["time"])
    return {
        "carbonIntensity": float(record["carbon_intensity"]),
        "datetime": ts,
        "updatedAt": ts,
        "createdAt": ts,
        "emissionFactorType": EMISSION_FACTOR_TYPE,
        "isEstimated": False,
        "estimationMethod": None,
    }


#######################################################################################################################
# The main API endpoints
#######################################################################################################################

@app.get("/carbon-intensity/current")
async def get_current_carbon_intensity(
    region: Annotated[Optional[str], Query(description="Country code (e.g., 'DE', 'US', 'FR')")] = None,
    simulationId: Annotated[Optional[str], Query(description="Simulation identifier")] = None,
    update: Annotated[bool, Query(description="If true, fetch fresh data before returning results")] = False,
    db: Connection = Depends(connection_dependency)) -> List[dict]:
    """Get current carbon grid intensity for a region or a simulation response."""

    if simulationId:
        return await get_simulation_carbon(simulationId=simulationId, db=db)

    region = _normalize_region(region)

    await _handle_update(update, region)

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
    region: Annotated[str, Query(..., description="Country code (e.g., 'DE', 'US', 'FR')")],
    simulationId: Annotated[Optional[str], Query(description="Simulation identifier")] = None,
    update: Annotated[bool, Query(description="If true, fetch fresh data before returning results.")] = False,
    db: Connection = Depends(connection_dependency),
) -> List[dict]:
    """Get current carbon grid intensity for the configured primary provider for the region."""

    if simulationId:
        return await get_simulation_carbon(simulationId=simulationId, db=db)

    region = _normalize_region(region)

    results = await get_current_carbon_intensity(region=region, update=update, db=db)
    print(results)

    primary_source = _get_primary_source(region)

    matched = [key for key in results if key.get("provider") == primary_source]

    if not matched:
        raise HTTPException(
            status_code=404,
            detail=f"No carbon intensity data available for primary provider '{primary_source}' in this region.",
        )

    return matched


@app.get("/carbon-intensity/history")
async def get_carbon_intensity_history(
    region: Annotated[str, Query(..., description="Country code (e.g., 'DE', 'US', 'FR')")],
    startTime: Annotated[str, Query(..., description="Start time in ISO 8601 format (e.g., '2025-09-22T10:00:00Z')")],
    endTime: Annotated[str, Query(..., description="End time in ISO 8601 format (e.g., '2025-09-22T12:00:00Z')")],
    provider: Annotated[Optional[str], Query(description="Optional filter by a provider")] = None,
    update: Annotated[bool|str, Query(description="If true, fetch fresh data before returning results. If string updates only that provider")] = False,
    simulationId: Annotated[Optional[str], Query(description="Simulation identifier")] = None,
    db: Connection = Depends(connection_dependency)
) -> List[dict]:
    """Get historical carbon grid intensity for a region and time range."""

    if simulationId:
        return await simulation_stats(simulationId=simulationId, db=db)

    if not startTime:
        raise HTTPException(status_code=400, detail="startTime parameter is required")

    if not endTime:
        raise HTTPException(status_code=400, detail="endTime parameter is required")

    region = _normalize_region(region)
    await _handle_update(update, region)

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
    results = fetch_between(db, region, start_dt, end_dt, provider)

    return results or []

#######################################################################################################################
# Simulation endpoints
#######################################################################################################################
@app.post("/simulation")
async def create_simulation(
    payload: SimulationCreateRequest, db: Connection = Depends(connection_dependency)
) -> dict:
    """Register a new simulation run with grid intensity values (optionally with per-value call counts)."""
    try:
        simulationId = simulation_store.create(payload.carbon_values, conn=db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"simulationId": simulationId}


@app.get("/simulation/get-carbon")
async def get_simulation_carbon(
    simulationId: Annotated[str, Query(..., description="Simulation identifier")],
    db: Connection = Depends(connection_dependency),
) -> dict:
    """Return the current simulated carbon intensity value (auto-advancing when call thresholds are met)."""
    try:
        value = simulation_store.current_value(simulationId, conn=db)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"simulationId": simulationId, "carbon_intensity": value}


@app.post("/simulation/next")
async def advance_simulation(
    simulationId: Annotated[str, Query(..., description="Simulation identifier")],
    db: Connection = Depends(connection_dependency),
) -> dict:
    """Advance a simulation to its next value."""
    try:
        value = simulation_store.advance(simulationId, conn=db)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SimulationExhaustedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"simulationId": simulationId, "carbon_intensity": value}


@app.get("/simulation/stats")
async def simulation_stats(
    simulationId: Annotated[str, Query(..., description="Simulation identifier")],
    db: Connection = Depends(connection_dependency),
) -> dict:
    """Return call history for a simulation."""
    try:
        return simulation_store.stats(simulationId, conn=db)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


#######################################################################################################################
# Electricity Maps compatible endpoints
#######################################################################################################################
@app.get("/v3/carbon-intensity/current")
async def get_v3_carbon_intensity_current(
    zone: Annotated[str, Query(..., description="Country code (e.g., 'DE', 'US', 'FR')")],
    auth_token: Annotated[Optional[str], Header(alias="auth-token")] = None,
    db: Connection = Depends(connection_dependency),
) -> Dict[str, Any]:
    """Electricity Maps compatible current carbon intensity response."""
    normalized_zone = _normalize_region(zone)

    if auth_token:
        sim_result = await get_simulation_carbon(simulationId=auth_token, db=db)
        return _format_em_current(normalized_zone, sim_result["carbon_intensity"])

    primary_result = get_primary_carbon_intensity(region=normalized_zone, update=False, db=db)
    primary = await primary_result if inspect.isawaitable(primary_result) else primary_result # We need to do this because of the monkeypatching in tests

    data = next(iter(primary.values()))
    timestamp = data.get("time") if isinstance(data, dict) else None

    return _format_em_current(normalized_zone, data.get("carbon_intensity"), timestamp=timestamp)


@app.get("/v3/carbon-intensity/history")
async def get_v3_carbon_intensity_history(
    zone: Annotated[str, Query(..., description="Country code (e.g., 'DE', 'US', 'FR')")],
    auth_token: Annotated[Optional[str], Header(alias="auth-token")] = None,
    db: Connection = Depends(connection_dependency),
) -> Dict[str, Any]:
    """Electricity Maps compatible 24h history response."""
    normalized_zone = _normalize_region(zone)

    if auth_token:
        sim_result = await get_simulation_carbon(simulationId=auth_token, db=db)
        now = datetime.now(timezone.utc)
        history_records = [
            {
                "carbon_intensity": sim_result["carbon_intensity"],
                "time": now,
            }
        ]
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=24)
        history_records = fetch_between(db, normalized_zone, start, end)

    return {
        "zone": normalized_zone,
        "history": [_format_em_history_entry(entry) for entry in history_records],
        "temporalGranularity": TEMPORAL_GRANULARITY,
    }


#######################################################################################################################
# MISC endpoints
#######################################################################################################################

@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve a simple dashboard for viewing carbon intensity data."""
    return HTMLResponse(INDEX_HTML)

@app.get("/regions")
async def list_regions(db: Connection = Depends(connection_dependency)) -> list[str]:
    """Return all regions with stored data."""
    return fetch_regions(db)

@app.get("/providers")
async def list_providers(db: Connection = Depends(connection_dependency)) -> list[tuple[str, str, str]]:
    #!pylint: disable=unused-argument
    """Return all providers with stored data."""
    return [
        (source.provider.lower(), source.region.upper(), f"{source.provider.lower()}_{source.region.lower()}")
        for source in config.cron.sources
    ]


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
