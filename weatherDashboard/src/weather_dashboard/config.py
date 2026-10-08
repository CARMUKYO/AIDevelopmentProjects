"""Configuration management for Weather Dashboard.

Precedence order:
    built-in defaults < TOML file < env vars (WEATHER_*) < CLI flags
"""

import os
import tomllib
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, ValidationInfo, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from weather_dashboard.errors import ConfigError

_current_toml_file: ContextVar[Path | None] = ContextVar("_current_toml_file", default=None)


def get_default_config_path() -> Path:
    """Return the default configuration file path based on XDG specification."""
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    base_dir = Path(xdg_home).expanduser() if xdg_home else Path.home() / ".config"
    return base_dir / "weather-dashboard" / "config.toml"


class WeatherTomlSettingsSource(TomlConfigSettingsSource):
    """Custom TOML settings source respecting context override or default XDG config path."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        file_path = _current_toml_file.get()
        if file_path is None:
            candidate = get_default_config_path()
            if candidate.is_file():
                file_path = candidate

        try:
            super().__init__(settings_cls, toml_file=file_path)
        except tomllib.TOMLDecodeError as err:
            target = file_path if file_path is not None else "unknown TOML file"
            raise ConfigError(f"Failed to parse TOML configuration from '{target}': {err}") from err


def _format_validation_error(exc: ValidationError) -> str:
    """Format Pydantic ValidationError into a user-facing string naming the offending key."""
    messages: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        if loc:
            messages.append(f"Invalid configuration for '{loc}': {msg}")
        else:
            messages.append(f"Invalid configuration: {msg}")
    return "; ".join(messages)


class Settings(BaseSettings):
    """Application settings for Weather Dashboard."""

    geocoding_base_url: str = Field(
        default="https://geocoding-api.open-meteo.com/v1",
        description="Base URL for Open-Meteo Geocoding API",
    )
    forecast_base_url: str = Field(
        default="https://api.open-meteo.com/v1",
        description="Base URL for Open-Meteo Forecast API",
    )
    connect_timeout: float = Field(
        default=5.0,
        gt=0,
        description="HTTP connect timeout in seconds",
    )
    read_timeout: float = Field(
        default=10.0,
        gt=0,
        description="HTTP read timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum number of retries for transient errors",
    )
    backoff_base: float = Field(
        default=0.5,
        gt=0,
        description="Base seconds for exponential backoff",
    )
    units: Literal["metric", "imperial"] = Field(
        default="metric",
        description="Measurement units: 'metric' or 'imperial'",
    )
    forecast_days: int = Field(
        default=7,
        ge=1,
        le=16,
        description="Number of forecast days (1 to 16)",
    )
    default_city: str | None = Field(
        default=None,
        description="Default city to query if none is provided on CLI",
    )
    user_agent: str = Field(
        default="weather-dashboard/0.1.0",
        min_length=1,
        description="HTTP User-Agent header",
    )

    model_config = SettingsConfigDict(
        env_prefix="WEATHER_",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            WeatherTomlSettingsSource(settings_cls),
        )

    def __init__(self, **values: Any) -> None:
        try:
            super().__init__(**values)
        except ValidationError as exc:
            raise ConfigError(_format_validation_error(exc)) from exc

    @field_validator("geocoding_base_url", "forecast_base_url")
    @classmethod
    def validate_url(cls, v: str, info: ValidationInfo) -> str:
        url = v.strip().rstrip("/")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"URL for '{info.field_name}' must start with http:// or https://")
        return url


def load_settings(config_path: Path | None = None, **cli_overrides: Any) -> Settings:
    """Load settings following precedence: defaults < TOML < env < CLI flags.

    Args:
        config_path: Explicit path to TOML configuration file.
        cli_overrides: CLI arguments to override lower precedence sources.
            Values of `None` are filtered out so defaults/env/file apply.

    Returns:
        Settings: Validated settings instance.

    Raises:
        ConfigError: If config file is missing, invalid TOML, or contains invalid values.
    """
    if config_path is not None:
        if not config_path.is_file():
            raise ConfigError(f"Configuration file not found: {config_path}")

    # Filter out None values so CLI defaults don't mask lower-precedence settings
    clean_overrides = {k: v for k, v in cli_overrides.items() if v is not None}

    token = _current_toml_file.set(config_path)
    try:
        return Settings(**clean_overrides)
    finally:
        _current_toml_file.reset(token)
