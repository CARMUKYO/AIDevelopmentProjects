"""Unit tests for configuration loading, precedence, and validation."""

from pathlib import Path

import pytest

from weather_dashboard.config import Settings, get_default_config_path, load_settings
from weather_dashboard.errors import ConfigError


def test_default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test built-in default values when no env or file is present."""
    # Ensure no interfering WEATHER_* env vars exist
    for key in (
        "WEATHER_GEOCODING_BASE_URL",
        "WEATHER_FORECAST_BASE_URL",
        "WEATHER_CONNECT_TIMEOUT",
        "WEATHER_READ_TIMEOUT",
        "WEATHER_MAX_RETRIES",
        "WEATHER_BACKOFF_BASE",
        "WEATHER_UNITS",
        "WEATHER_FORECAST_DAYS",
        "WEATHER_DEFAULT_CITY",
        "WEATHER_USER_AGENT",
    ):
        monkeypatch.delenv(key, raising=False)

    # Point XDG to an empty temp directory so no user config.toml is read
    monkeypatch.setenv("XDG_CONFIG_HOME", "/nonexistent/xdg/path")

    settings = load_settings()
    assert settings.geocoding_base_url == "https://geocoding-api.open-meteo.com/v1"
    assert settings.forecast_base_url == "https://api.open-meteo.com/v1"
    assert settings.connect_timeout == 5.0
    assert settings.read_timeout == 10.0
    assert settings.max_retries == 3
    assert settings.backoff_base == 0.5
    assert settings.units == "metric"
    assert settings.forecast_days == 7
    assert settings.default_city is None
    assert settings.user_agent == "weather-dashboard/0.1.0"


def test_toml_overrides_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a TOML config file overrides default values."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    toml_file = tmp_path / "custom_config.toml"
    toml_file.write_text(
        """
        units = "imperial"
        forecast_days = 3
        default_city = "Seattle"
        connect_timeout = 2.5
        """
    )

    settings = load_settings(config_path=toml_file)
    assert settings.units == "imperial"
    assert settings.forecast_days == 3
    assert settings.default_city == "Seattle"
    assert settings.connect_timeout == 2.5
    # Non-overridden fields retain defaults
    assert settings.read_timeout == 10.0


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that WEATHER_* env vars override values from TOML."""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(
        """
        units = "imperial"
        forecast_days = 3
        default_city = "Tokyo"
        """
    )

    monkeypatch.setenv("WEATHER_UNITS", "metric")
    monkeypatch.setenv("WEATHER_FORECAST_DAYS", "10")
    # default_city is NOT set in env, so TOML value should survive

    settings = load_settings(config_path=toml_file)
    assert settings.units == "metric"
    assert settings.forecast_days == 10
    assert settings.default_city == "Tokyo"


def test_cli_overrides_env_and_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that CLI arguments have the highest precedence."""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(
        """
        units = "metric"
        forecast_days = 3
        default_city = "London"
        """
    )

    monkeypatch.setenv("WEATHER_UNITS", "imperial")
    monkeypatch.setenv("WEATHER_FORECAST_DAYS", "5")

    # CLI overrides forecast_days and units
    settings = load_settings(
        config_path=toml_file,
        forecast_days=14,
        units="metric",
        default_city=None,  # None should NOT override TOML
    )

    assert settings.forecast_days == 14
    assert settings.units == "metric"
    assert settings.default_city == "London"


def test_xdg_config_path_discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that default config path uses $XDG_CONFIG_HOME."""
    fake_xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_xdg))

    expected_path = fake_xdg / "weather-dashboard" / "config.toml"
    assert get_default_config_path() == expected_path

    # Put a config file there and verify load_settings picks it up automatically
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    expected_path.write_text('default_city = "Reykjavik"\n')

    settings = load_settings()
    assert settings.default_city == "Reykjavik"


def test_missing_explicit_config_file_raises_config_error(tmp_path: Path) -> None:
    """Test that specifying a nonexistent config file raises ConfigError."""
    nonexistent = tmp_path / "does_not_exist.toml"
    with pytest.raises(ConfigError, match="Configuration file not found"):
        load_settings(config_path=nonexistent)


def test_invalid_toml_syntax_raises_config_error(tmp_path: Path) -> None:
    """Test that a corrupt TOML file raises ConfigError."""
    bad_toml = tmp_path / "bad.toml"
    bad_toml.write_text("invalid = toml content ===")
    with pytest.raises(ConfigError, match="Failed to parse TOML configuration"):
        load_settings(config_path=bad_toml)


@pytest.mark.parametrize(
    ("key", "val"),
    [
        ("forecast_days", 0),
        ("forecast_days", 17),
        ("units", "celsius"),
        ("connect_timeout", 0),
        ("connect_timeout", -1.0),
        ("read_timeout", 0),
        ("max_retries", -1),
        ("backoff_base", 0),
        ("geocoding_base_url", "ftp://example.com"),
        ("user_agent", ""),
    ],
)
def test_invalid_values_raise_config_error_with_key_name(key: str, val: object) -> None:
    """Test that out-of-range or invalid values raise ConfigError naming the offending key."""
    with pytest.raises(ConfigError) as exc_info:
        Settings(**{key: val})

    assert key in str(exc_info.value)


def test_invalid_env_var_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that invalid values in environment variables raise ConfigError naming the key."""
    monkeypatch.setenv("WEATHER_FORECAST_DAYS", "0")
    with pytest.raises(ConfigError) as exc_info:
        load_settings()

    assert "forecast_days" in str(exc_info.value)


def test_example_config_file_is_valid() -> None:
    """Test that config.example.toml in the repo is valid and loadable."""
    example_path = Path("config.example.toml")
    assert example_path.is_file()
    settings = load_settings(config_path=example_path)
    assert settings.units == "metric"
    assert settings.forecast_days == 7
