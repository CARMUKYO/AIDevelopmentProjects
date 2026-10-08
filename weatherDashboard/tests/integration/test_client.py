"""Integration tests for OpenMeteoClient using respx mocking."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from respx import MockRouter

from weather_dashboard.client import OpenMeteoClient
from weather_dashboard.config import Settings
from weather_dashboard.errors import (
    ApiRequestError,
    ApiTimeout,
    ApiUnavailable,
    LocationNotFound,
    UnexpectedResponse,
)
from weather_dashboard.http import build_client

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def load_fixture(filename: str) -> dict[str, Any]:
    """Load JSON test fixture from tests/fixtures."""
    return json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


class MockSleepRecorder:
    """Mock sleep function to verify delays without delaying tests."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, delay: float) -> None:
        self.delays.append(delay)


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings instance."""
    return Settings(
        geocoding_base_url="https://geocoding-api.open-meteo.com/v1",
        forecast_base_url="https://api.open-meteo.com/v1",
        connect_timeout=2.0,
        read_timeout=3.0,
        max_retries=2,
        backoff_base=0.1,
        units="metric",
        forecast_days=7,
        user_agent="weather-test/1.0",
    )


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_geocode_happy_path(respx_mock: MockRouter, test_settings: Settings) -> None:
    """Test successful geocoding returning domain Location."""
    payload = load_fixture("geocoding_valid.json")
    route = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json=payload,
        )
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings)
        location = client.geocode("Naga")

    assert location.name == "Naga"
    assert location.country == "Philippines"
    assert location.latitude == 13.61917
    assert location.longitude == 123.18139
    assert route.call_count == 1


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_forecast_happy_path(respx_mock: MockRouter, test_settings: Settings) -> None:
    """Test successful forecast retrieval."""
    payload = load_fixture("forecast_valid.json")
    route = respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json=payload,
        )
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings)
        forecast = client.forecast(13.62, 123.18, days=3, units="metric")

    assert forecast.latitude == 13.62
    assert forecast.longitude == 123.18
    assert forecast.current.temperature_2m == 29.4
    assert len(forecast.daily.time) == 3
    assert route.call_count == 1


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_forecast_imperial_units_query_params(
    respx_mock: MockRouter, test_settings: Settings
) -> None:
    """Test that imperial units set correct query params for Open-Meteo."""
    payload = load_fixture("forecast_valid.json")
    route = respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json=payload,
        )
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings)
        client.forecast(14.6, 120.98, days=5, units="imperial")

    assert route.call_count == 1
    last_req = route.calls.last.request
    assert "temperature_unit=fahrenheit" in str(last_req.url)
    assert "wind_speed_unit=mph" in str(last_req.url)
    assert "precipitation_unit=inch" in str(last_req.url)
    assert "forecast_days=5" in str(last_req.url)


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_geocode_city_not_found_no_results_key(
    respx_mock: MockRouter, test_settings: Settings
) -> None:
    """Test geocoding error when response has no results key (LocationNotFound exit 3)."""
    payload = load_fixture("geocoding_no_results.json")
    route = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json=payload,
        )
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings)
        with pytest.raises(LocationNotFound, match="Location not found for city: 'Nonexistent'"):
            client.geocode("Nonexistent")

    assert route.call_count == 1


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_geocode_city_not_found_empty_results(
    respx_mock: MockRouter, test_settings: Settings
) -> None:
    """Test geocoding error when results is an empty array."""
    payload = load_fixture("geocoding_empty_results.json")
    route = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json=payload,
        )
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings)
        with pytest.raises(LocationNotFound):
            client.geocode("EmptyCity")

    assert route.call_count == 1


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_connect_and_read_timeout_retries_exhausted(
    respx_mock: MockRouter, test_settings: Settings
) -> None:
    """Test ConnectTimeout and ReadTimeout exhaustion raises ApiTimeout."""
    sleep_recorder = MockSleepRecorder()
    route = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        side_effect=httpx.ConnectTimeout("Connection timed out")
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings, sleep_fn=sleep_recorder)
        with pytest.raises(ApiTimeout, match="timed out after 2 retries"):
            client.geocode("Naga")

    # max_retries = 2 -> 3 total calls (initial + 2 retries)
    assert route.call_count == 3
    assert len(sleep_recorder.delays) == 2


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_network_connect_error_retries_exhausted(
    respx_mock: MockRouter, test_settings: Settings
) -> None:
    """Test network error (DNS/Connection failure) exhaustion raises ApiUnavailable."""
    sleep_recorder = MockSleepRecorder()
    route = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        side_effect=httpx.ConnectError("Failed to resolve host")
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings, sleep_fn=sleep_recorder)
        with pytest.raises(ApiUnavailable, match="API network error after 2 retries"):
            client.geocode("Naga")

    assert route.call_count == 3
    assert len(sleep_recorder.delays) == 2


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_retry_500_then_success(respx_mock: MockRouter, test_settings: Settings) -> None:
    """Test 500 error followed by 200 OK succeeds on retry (call count == 2)."""
    sleep_recorder = MockSleepRecorder()
    payload = load_fixture("geocoding_valid.json")

    route = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        side_effect=[
            httpx.Response(500, text="Internal Server Error"),
            httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                json=payload,
            ),
        ]
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings, sleep_fn=sleep_recorder)
        loc = client.geocode("Naga")

    assert loc.name == "Naga"
    assert route.call_count == 2
    assert len(sleep_recorder.delays) == 1


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_retry_503_exhausted_raises_api_unavailable(
    respx_mock: MockRouter, test_settings: Settings
) -> None:
    """Test persistent 503 error exhausts max_retries + 1 calls and raises ApiUnavailable."""
    sleep_recorder = MockSleepRecorder()
    route = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings, sleep_fn=sleep_recorder)
        with pytest.raises(ApiUnavailable, match="HTTP 503 returned after 2 retries"):
            client.geocode("Naga")

    assert route.call_count == 3
    assert len(sleep_recorder.delays) == 2


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_retry_429_with_retry_after_header(respx_mock: MockRouter, test_settings: Settings) -> None:
    """Test 429 Too Many Requests honours Retry-After header then succeeds."""
    sleep_recorder = MockSleepRecorder()
    payload = load_fixture("geocoding_valid.json")

    route = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        side_effect=[
            httpx.Response(
                429,
                headers={"Retry-After": "2", "Content-Type": "application/json"},
                text='{"error": true}',
            ),
            httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                json=payload,
            ),
        ]
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings, sleep_fn=sleep_recorder)
        loc = client.geocode("Naga")

    assert loc.name == "Naga"
    assert route.call_count == 2
    assert len(sleep_recorder.delays) == 1
    assert sleep_recorder.delays[0] == 2.0


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_api_request_error_400_with_reason(respx_mock: MockRouter, test_settings: Settings) -> None:
    """Test HTTP 400 with Open-Meteo reason raises ApiRequestError without retrying."""
    sleep_recorder = MockSleepRecorder()
    error_payload = load_fixture("api_error_400.json")

    route = respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(
            400,
            headers={"Content-Type": "application/json"},
            json=error_payload,
        )
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings, sleep_fn=sleep_recorder)
        with pytest.raises(ApiRequestError, match="Latitude must be in range of -90 to 90°"):
            client.forecast(999.0, 120.98)

    assert route.call_count == 1
    assert len(sleep_recorder.delays) == 0


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_api_request_error_404_no_retry(respx_mock: MockRouter, test_settings: Settings) -> None:
    """Test HTTP 404 raises ApiRequestError immediately without retrying."""
    sleep_recorder = MockSleepRecorder()
    route = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(404, text="Not Found")
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings, sleep_fn=sleep_recorder)
        with pytest.raises(ApiRequestError, match="HTTP 404"):
            client.geocode("Naga")

    assert route.call_count == 1
    assert len(sleep_recorder.delays) == 0


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_unexpected_response_html_body(respx_mock: MockRouter, test_settings: Settings) -> None:
    """Test response with HTML content type raises UnexpectedResponse without retrying."""
    sleep_recorder = MockSleepRecorder()
    route = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            text="<html><body>Bad Gateway</body></html>",
        )
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings, sleep_fn=sleep_recorder)
        with pytest.raises(UnexpectedResponse, match="Unexpected Content-Type"):
            client.geocode("Naga")

    assert route.call_count == 1
    assert len(sleep_recorder.delays) == 0


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_unexpected_response_empty_body(respx_mock: MockRouter, test_settings: Settings) -> None:
    """Test empty body raises UnexpectedResponse."""
    route = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            text="   ",
        )
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings)
        with pytest.raises(UnexpectedResponse, match="Unexpected empty response body"):
            client.geocode("Naga")

    assert route.call_count == 1


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_unexpected_response_invalid_json(respx_mock: MockRouter, test_settings: Settings) -> None:
    """Test non-JSON body with application/json header raises UnexpectedResponse."""
    route = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            text="not-valid-json",
        )
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings)
        with pytest.raises(UnexpectedResponse, match="Failed to parse response body as JSON"):
            client.geocode("Naga")

    assert route.call_count == 1


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_unexpected_response_mismatched_arrays(
    respx_mock: MockRouter, test_settings: Settings
) -> None:
    """Test mismatched array lengths in forecast payload raises UnexpectedResponse."""
    mismatched_payload = load_fixture("forecast_mismatched_arrays.json")
    route = respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json=mismatched_payload,
        )
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings)
        with pytest.raises(UnexpectedResponse, match="Mismatched array length"):
            client.forecast(13.62, 123.18)

    assert route.call_count == 1


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_unexpected_response_missing_fields(
    respx_mock: MockRouter, test_settings: Settings
) -> None:
    """Test missing required fields in forecast payload raises UnexpectedResponse."""
    missing_payload = load_fixture("forecast_missing_field.json")
    route = respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json=missing_payload,
        )
    )

    with build_client(test_settings) as http_client:
        client = OpenMeteoClient(http_client, test_settings)
        with pytest.raises(UnexpectedResponse, match="schema validation"):
            client.forecast(13.62, 123.18)

    assert route.call_count == 1
