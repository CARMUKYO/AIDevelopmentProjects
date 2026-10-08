"""Domain exception hierarchy for Weather Dashboard."""


class WeatherError(Exception):
    """Base exception for all weather dashboard domain errors."""

    exit_code: int = 1

    def __init__(self, message: str, exit_code: int | None = None) -> None:
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code


class ConfigError(WeatherError):
    """Invalid/missing config, bad TOML, out-of-range values."""

    exit_code = 2


class LocationNotFound(WeatherError):
    """Geocoding returns no results."""

    exit_code = 3


class ApiTimeout(WeatherError):
    """Connect/read timeout after retries exhausted."""

    exit_code = 4


class ApiUnavailable(WeatherError):
    """Network error, DNS failure, HTTP 5xx after retries, HTTP 429."""

    exit_code = 4


class ApiRequestError(WeatherError):
    """HTTP 4xx (include Open-Meteo reason if present)."""

    exit_code = 5


class UnexpectedResponse(WeatherError):
    """Non-JSON body, wrong content type, schema validation failure, missing/mismatched fields."""

    exit_code = 6
