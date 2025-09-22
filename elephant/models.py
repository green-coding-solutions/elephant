"""Data models for Elephant service."""

from datetime import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field, field_validator, ConfigDict


class CarbonIntensityResponse(BaseModel):
    """Standard response model for carbon intensity data."""

    location: str
    time: dt
    carbonIntensity: float = Field(alias="carbon_intensity")

    @field_validator("carbonIntensity")
    @classmethod
    def validate_carbon_intensity(cls, v: float) -> float:
        """Validate carbon intensity is within acceptable bounds."""
        if not 0 <= v <= 1000:
            raise ValueError("Carbon intensity must be between 0-1000 gCO2/kWh")
        return v

    model_config = ConfigDict(populate_by_name=True)


class ElectricityMapsResponse(BaseModel):
    """Response model for ElectricityMaps API."""

    zone: str
    carbonIntensity: float
    datetime: dt
    updatedAt: dt
    createdAt: dt
    emissionFactorType: str
    isEstimated: bool
    estimationMethod: Optional[str] = None
    temporalGranularity: str
