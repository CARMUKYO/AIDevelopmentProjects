"""Open-Meteo API HTTP client with retries, exponential backoff, and defensive validation."""

import json
import random
import time
from typing import Any

import httpx
from pydantic import ValidationError

from weather_dashboard.config import Settings
from weather_dashboard.errors import (
    ApiRequestError,
    ApiTimeout,
    ApiUnavailable,
    ConfigError,
    LocationNotFound,
    UnexpectedResponse,
)
from weather_dashboard.http import SleepCallable
from weather_dashboard.models import (
    ForecastResponse,
    GeocodingResponse,
    Location,
    map_geocoding_to_location,
)

RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class OpenMeteoClient:
    """Client for interacting with Open-Meteo Geocoding and Forecast APIs.

    This is the only module in the application that performs HTTP operations.
    """

    def __init__(
        self,
        client: httpx.Client,
        settings: Settings,
        sleep_fn: SleepCallable = time.sleep,
        max_delay: float = 60.0,
    ) -> None:
        self.client = client
        self.settings = settings
        self.sleep_fn = sleep_fn
        self.max_delay = max_delay

    def geocode(self, city: str) -> Location:
        """Geocode a city name into geographic coordinates.

        Args:
            city: Name of the city to search.

        Returns:
            Location: Domain model representing the top search match.

        Raises:
            LocationNotFound: If no results are returned for the city.
            ApiTimeout: If requests time out and retries are exhausted.
            ApiUnavailable: If network or server errors persist after retries.
            ApiRequestError: On 4xx HTTP responses.
            UnexpectedResponse: On malformed, non-JSON, or schema-invalid responses.
        """
        clean_city = city.strip()
        if not clean_city:
            raise LocationNotFound("Empty city query")

        url = f"{self.settings.geocoding_base_url}/search"
        params: dict[str, Any] = {
            "name": clean_city,
            "count": 1,
            "language": "en",
            "format": "json",
        }

        response = self._get_with_retry(url, params=params)
        data = self._parse_json_payload(response)

        try:
            parsed = GeocodingResponse.model_validate(data)
        except ValidationError as exc:
            raise UnexpectedResponse(f"Geocoding response failed schema validation: {exc}") from exc

        if not parsed.results:
            raise LocationNotFound(f"Location not found for city: '{clean_city}'")

        return map_geocoding_to_location(parsed.results[0])

    def forecast(
        self,
        latitude: float,
        longitude: float,
        days: int | None = None,
        units: str | None = None,
    ) -> ForecastResponse:
        """Fetch current weather and daily forecast for a given latitude and longitude.

        Args:
            latitude: Geographic latitude (-90.0 to 90.0).
            longitude: Geographic longitude (-180.0 to 180.0).
            days: Number of forecast days (1 to 16). Defaults to settings.forecast_days.
            units: 'metric' or 'imperial'. Defaults to settings.units.

        Returns:
            ForecastResponse: Validated raw forecast payload.

        Raises:
            ConfigError: If days or units are out of allowed ranges.
            ApiTimeout: If requests time out and retries are exhausted.
            ApiUnavailable: If network or server errors persist after retries.
            ApiRequestError: On 4xx HTTP responses (including Open-Meteo reasons).
            UnexpectedResponse: On malformed, non-JSON, or schema-invalid responses.
        """
        forecast_days = days if days is not None else self.settings.forecast_days
        if forecast_days < 1 or forecast_days > 16:
            raise ConfigError(
                f"Invalid 'forecast_days': {forecast_days}. Must be between 1 and 16."
            )

        unit_system = units if units is not None else self.settings.units
        if unit_system not in ("metric", "imperial"):
            raise ConfigError(f"Invalid 'units': {unit_system}. Must be 'metric' or 'imperial'.")

        url = f"{self.settings.forecast_base_url}/forecast"
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,"
                "apparent_temperature,weather_code,wind_speed_10m"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            ),
            "forecast_days": forecast_days,
            "timezone": "auto",
        }

        if unit_system == "imperial":
            params["temperature_unit"] = "fahrenheit"
            params["wind_speed_unit"] = "mph"
            params["precipitation_unit"] = "inch"

        response = self._get_with_retry(url, params=params)
        data = self._parse_json_payload(response)

        try:
            return ForecastResponse.model_validate(data)
        except ValidationError as exc:
            raise UnexpectedResponse(f"Forecast response failed schema validation: {exc}") from exc

    def _get_with_retry(self, url: str, params: dict[str, Any]) -> httpx.Response:
        """Execute GET request with exponential backoff, jitter, and status-code validation."""
        total_attempts = self.settings.max_retries + 1

        for attempt in range(total_attempts):
            is_last_attempt = attempt == self.settings.max_retries

            try:
                response = self.client.get(url, params=params)
                status = response.status_code

                # Retriable server error or rate-limit status codes
                if status in RETRIABLE_STATUS_CODES:
                    if is_last_attempt:
                        msg = (
                            f"API unavailable: HTTP {status} returned after "
                            f"{self.settings.max_retries} retries"
                        )
                        raise ApiUnavailable(msg)
                    delay = self._compute_delay(response, attempt)
                    self.sleep_fn(delay)
                    continue

                # Non-retriable 4xx client errors
                if 400 <= status < 500:
                    reason = self._extract_error_reason(response)
                    if reason:
                        raise ApiRequestError(f"API request error: {reason}")
                    raise ApiRequestError(f"API request failed with HTTP {status}: {response.text}")

                # Retriable other 5xx status codes
                if status >= 500:
                    if is_last_attempt:
                        msg = (
                            f"API unavailable: HTTP {status} returned after "
                            f"{self.settings.max_retries} retries"
                        )
                        raise ApiUnavailable(msg)
                    delay = self._compute_delay(response, attempt)
                    self.sleep_fn(delay)
                    continue

                # Success (2xx)
                return response

            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout) as exc:
                if is_last_attempt:
                    raise ApiTimeout(
                        f"API request timed out after {self.settings.max_retries} retries: {exc}"
                    ) from exc
                delay = self._compute_delay(None, attempt)
                self.sleep_fn(delay)

            except (httpx.ConnectError, httpx.NetworkError) as exc:
                if is_last_attempt:
                    raise ApiUnavailable(
                        f"API network error after {self.settings.max_retries} retries: {exc}"
                    ) from exc
                delay = self._compute_delay(None, attempt)
                self.sleep_fn(delay)

            except httpx.HTTPError as exc:
                if is_last_attempt:
                    raise ApiUnavailable(
                        f"HTTP communication error after {self.settings.max_retries} retries: {exc}"
                    ) from exc
                delay = self._compute_delay(None, attempt)
                self.sleep_fn(delay)

        raise ApiUnavailable("Request failed after exhausting retries")

    def _compute_delay(self, response: httpx.Response | None, attempt: int) -> float:
        """Calculate backoff delay respecting Retry-After header and applying exponential jitter."""
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            if retry_after is not None:
                try:
                    val = float(retry_after)
                    return float(min(val, self.max_delay))
                except ValueError:
                    pass

        base_backoff = self.settings.backoff_base * (2**attempt)
        jitter = random.uniform(0.0, 0.1 * self.settings.backoff_base)
        delay = float(base_backoff + jitter)
        return float(min(delay, self.max_delay))

    def _extract_error_reason(self, response: httpx.Response) -> str | None:
        """Try to extract Open-Meteo error reason string from 400 responses."""
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type.lower():
            try:
                data = response.json()
                if isinstance(data, dict):
                    reason = data.get("reason")
                    if isinstance(reason, str) and reason.strip():
                        return reason.strip()
            except Exception:
                pass
        return None

    def _parse_json_payload(self, response: httpx.Response) -> dict[str, Any]:
        """Defensively validate HTTP headers, content type, and parse JSON body."""
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            raise UnexpectedResponse(
                f"Unexpected Content-Type '{content_type}', expected 'application/json'"
            )

        content = response.content
        if not content.strip():
            raise UnexpectedResponse("Unexpected empty response body")

        try:
            parsed: Any = json.loads(content.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise UnexpectedResponse(f"Failed to parse response body as JSON: {exc}") from exc

        if not isinstance(parsed, dict):
            raise UnexpectedResponse(f"Expected JSON object at root, got {type(parsed).__name__}")

        return parsed
