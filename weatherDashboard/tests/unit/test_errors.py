"""Unit tests for domain error classes."""

from weather_dashboard.errors import (
    ApiRequestError,
    ApiTimeout,
    ApiUnavailable,
    ConfigError,
    LocationNotFound,
    UnexpectedResponse,
    WeatherError,
)


def test_weather_error_hierarchy() -> None:
    """Test domain error exit codes and inheritance."""
    assert issubclass(ConfigError, WeatherError)
    assert issubclass(LocationNotFound, WeatherError)
    assert issubclass(ApiTimeout, WeatherError)
    assert issubclass(ApiUnavailable, WeatherError)
    assert issubclass(ApiRequestError, WeatherError)
    assert issubclass(UnexpectedResponse, WeatherError)

    assert ConfigError.exit_code == 2
    assert LocationNotFound.exit_code == 3
    assert ApiTimeout.exit_code == 4
    assert ApiUnavailable.exit_code == 4
    assert ApiRequestError.exit_code == 5
    assert UnexpectedResponse.exit_code == 6


def test_custom_exit_code_and_message() -> None:
    """Test custom exit code override and error message."""
    err = WeatherError("Something failed", exit_code=99)
    assert str(err) == "Something failed"
    assert err.exit_code == 99

    default_err = ConfigError("Bad config")
    assert str(default_err) == "Bad config"
    assert default_err.exit_code == 2
