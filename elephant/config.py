"""Configuration management for Elephant service."""

import logging
from pathlib import Path
from typing import Dict, Optional, Any

import yaml
from pydantic import BaseModel, Field, field_validator


logger = logging.getLogger(__name__)


class ProviderConfig(BaseModel):
    """Configuration for a carbon intensity provider."""

    enabled: bool = False
    base_url: str
    api_token: Optional[str] = None

    @field_validator("api_token")
    @classmethod
    def validate_api_token(cls, v: Optional[str], info: Any) -> Optional[str]:
        """Validate API token requirements based on provider type and base URL."""
        if not info.data.get("enabled"):
            return v

        base_url = info.data.get("base_url", "")

        # ElectricityMaps requires API token
        if "electricitymaps.com" in base_url:
            if not v:
                raise ValueError("ElectricityMaps provider requires an API token")
            if "your-electricitymaps-api-token-here" in v:
                raise ValueError("ElectricityMaps API token must be replaced with your actual token")

        # Carbon-Aware-Computing requires API token
        if "carbon-aware-computing.com" in base_url:
            if not v:
                raise ValueError("Carbon-Aware-Computing provider requires an API token")
            if "your-carbon-aware-computing-api-token-here" in v:
                raise ValueError("Carbon-Aware-Computing API token must be replaced with your actual token")

        # Carbon-Aware-SDK (local) doesn't require token
        # Other providers can be added here with their specific requirements

        return v


class SimulationConfig(BaseModel):
    """Configuration for simulation features."""

    session_expiry_hours: int = Field(default=1, ge=1)
    max_data_points: int = Field(default=1000, ge=1)
    max_concurrent_sessions: int = Field(default=100, ge=1)
    time_unit: str = Field(default="seconds")
    cleanup_interval_minutes: int = Field(default=15, ge=1)


class CacheConfig(BaseModel):
    """Configuration for data caching."""

    retention_hours: int = Field(default=24, ge=1)


class PollingConfig(BaseModel):
    """Configuration for background polling."""

    enabled: bool = True
    interval_minutes: int = Field(default=5, ge=1)


class LoggingConfig(BaseModel):
    """Configuration for logging."""

    level: str = Field(default="INFO")


class Config(BaseModel):
    """Main configuration for Elephant service."""

    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = Path("config.yml")

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}. "
            f"Copy config.example.yml to config.yml and configure your API tokens."
        )

    logger.info("Loading configuration from %s", config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    try:
        return Config(**config_data)
    except Exception as e:
        raise ValueError(f"Invalid configuration: {e}") from e
