"""Tests for configuration management."""

import pytest
import tempfile
from pathlib import Path

from elephant.config import Config, ProviderConfig, load_config


class TestProviderConfig:
    """Tests for provider configuration validation."""

    def test_electricitymaps_requires_token(self) -> None:
        """Test that ElectricityMaps provider requires API token."""
        with pytest.raises(ValueError, match="ElectricityMaps provider requires an API token"):
            ProviderConfig(enabled=True, base_url="https://api.electricitymaps.com", api_token=None)

    def test_electricitymaps_rejects_placeholder_token(self) -> None:
        """Test that ElectricityMaps provider rejects placeholder token."""
        with pytest.raises(ValueError, match="ElectricityMaps API token must be replaced with your actual token"):
            ProviderConfig(
                enabled=True,
                base_url="https://api.electricitymaps.com",
                api_token="your-electricitymaps-api-token-here",
            )

    def test_carbon_aware_computing_requires_token(self) -> None:
        """Test that Carbon-Aware-Computing provider requires API token."""
        with pytest.raises(ValueError, match="Carbon-Aware-Computing provider requires an API token"):
            ProviderConfig(enabled=True, base_url="https://intensity.carbon-aware-computing.com", api_token=None)

    def test_carbon_aware_computing_rejects_placeholder_token(self) -> None:
        """Test that Carbon-Aware-Computing provider rejects placeholder token."""
        with pytest.raises(
            ValueError, match="Carbon-Aware-Computing API token must be replaced with your actual token"
        ):
            ProviderConfig(
                enabled=True,
                base_url="https://intensity.carbon-aware-computing.com",
                api_token="your-carbon-aware-computing-api-token-here",
            )

    def test_carbon_aware_sdk_no_token_required(self) -> None:
        """Test that Carbon-Aware-SDK (local) doesn't require API token."""
        config = ProviderConfig(enabled=True, base_url="http://localhost:8080", api_token=None)
        assert config.enabled
        assert config.api_token is None

    def test_valid_tokens_accepted(self) -> None:
        """Test that valid API tokens are accepted."""
        # ElectricityMaps with valid token
        config1 = ProviderConfig(
            enabled=True, base_url="https://api.electricitymaps.com", api_token="abc123-real-token"
        )
        assert config1.enabled
        assert config1.api_token == "abc123-real-token"

        # Carbon-Aware-Computing with valid token
        config2 = ProviderConfig(
            enabled=True, base_url="https://intensity.carbon-aware-computing.com", api_token="xyz789-real-token"
        )
        assert config2.enabled
        assert config2.api_token == "xyz789-real-token"

    def test_disabled_provider_no_token_required(self) -> None:
        """Test that disabled provider doesn't require API token regardless of type."""
        config = ProviderConfig(enabled=False, base_url="https://api.electricitymaps.com", api_token=None)
        assert not config.enabled
        assert config.api_token is None


class TestConfig:
    """Tests for main configuration validation."""

    def test_no_enabled_providers_allowed(self) -> None:
        """Test that configuration allows zero enabled providers (simulation-only mode)."""
        config: Config = Config(
            providers={"test": ProviderConfig(enabled=False, base_url="https://api.example.com", api_token="token")}
        )
        assert len(config.providers) == 1
        assert not config.providers["test"].enabled  # pylint: disable=unsubscriptable-object

    def test_empty_providers_allowed(self) -> None:
        """Test that configuration allows completely empty providers (simulation-only mode)."""
        config = Config(providers={})
        assert len(config.providers) == 0

    def test_valid_config_with_enabled_provider(self) -> None:
        """Test valid configuration with enabled provider."""
        config = Config(
            providers={
                "electricitymaps": ProviderConfig(
                    enabled=True, base_url="https://api.electricitymaps.com", api_token="test-token"
                )
            }
        )
        assert len(config.providers) == 1
        assert config.providers["electricitymaps"].enabled  # pylint: disable=unsubscriptable-object

    def test_provider_access_via_get_method(self) -> None:
        """Test that providers can be accessed via dict.get() method for initialization."""
        config = Config(
            providers={
                "electricitymaps": ProviderConfig(
                    enabled=True, base_url="https://api.electricitymaps.com", api_token="test-token"
                ),
                "carbon_aware_sdk": ProviderConfig(enabled=False, base_url="http://localhost:8080", api_token=None),
            }
        )

        # Test that .get() method works (this is what app.py uses)
        electricitymaps_config = config.providers.get("electricitymaps")  # pylint: disable=no-member
        assert electricitymaps_config is not None
        assert electricitymaps_config.enabled

        # Test that .get() returns None for non-existent providers
        nonexistent_config = config.providers.get("nonexistent")  # pylint: disable=no-member
        assert nonexistent_config is None

        # Test that disabled provider is still accessible but disabled
        carbon_aware_config = config.providers.get("carbon_aware_sdk")  # pylint: disable=no-member
        assert carbon_aware_config is not None
        assert not carbon_aware_config.enabled


class TestLoadConfig:
    """Tests for configuration loading."""

    def test_load_valid_config(self) -> None:
        """Test loading valid configuration from file."""
        config_content = """
providers:
  electricitymaps:
    enabled: true
    base_url: "https://api.electricitymaps.com"
    api_token: "test-token"

logging:
  level: "DEBUG"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(config_content)
            f.flush()

            config = load_config(Path(f.name))

            assert config.providers["electricitymaps"].enabled  # pylint: disable=unsubscriptable-object
            assert config.logging.level == "DEBUG"  # pylint: disable=no-member

    def test_load_missing_file_raises_error(self) -> None:
        """Test that missing config file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_config(Path("nonexistent.yml"))

    def test_load_invalid_yaml_raises_error(self) -> None:
        """Test that invalid YAML raises ValueError."""
        config_content = """
providers:
  electricitymaps:
    enabled: true
    # Missing required fields
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ValueError, match="Invalid configuration"):
                load_config(Path(f.name))
