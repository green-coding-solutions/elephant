"""Configuration management for Elephant service."""

import logging
from pathlib import Path
from typing import Dict, Optional

import yaml
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yml"


class ProviderConfig(BaseModel):
    """Configuration for a carbon intensity provider."""

    enabled: bool = False
    api_token: Optional[str] = None

class DatabaseConfig(BaseModel):
    """Configuration for the database."""

    url: str

class Source(BaseModel):
    """Configuration for a region to fetch data for."""

    region: str
    provider: str
    primary: bool = False

class CronConfig(BaseModel):
    """Configuration for background polling."""

    interval_seconds: int = Field(default=300, ge=1)
    sources: list[Source] = Field(default_factory=list)


class LoggingConfig(BaseModel):
    """Configuration for logging."""

    level: str = Field(default="INFO")


class Config(BaseModel):
    """Main configuration for Elephant service."""

    database: DatabaseConfig
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    cron: CronConfig = Field(default_factory=CronConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

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


try:
    # Load configuration eagerly so callers can simply import `config`
    config: Config = load_config()
except Exception:
    logger.exception("Failed to load configuration")
    raise
