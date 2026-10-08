"""Unit tests for raw and domain data models."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from weather_dashboard.models import (
    DailyForecastRaw,
    ForecastResponse,
    GeocodingResponse,
    Location,
    get_wmo_description,
    map_forecast_to_dashboard,
    map_geocoding_to_location,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def load_fixture(filename: str) -> dict[str, object]:
    """Load JSON test fixture from tests/fixtures."""
    path = FIXTURES_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_wmo_code_mapping() -> None:
    """Test WMO weather code mapping including unknown and null codes."""
    assert get_wmo_description(0) == "Clear sky"
    assert get_wmo_description(2) == "Partly cloudy"
    assert get_wmo_description(61) == "Rain: Slight"
    assert get_wmo_description(95) == "Thunderstorm: Slight or moderate"

    # Unknown codes and None
    assert get_wmo_description(999) == "Unknown"
    assert get_wmo_description(-1) == "Unknown"
    assert get_wmo_description(None) == "Unknown"


def test_geocoding_valid_payload() -> None:
    """Test parsing valid geocoding payload with extra fields ignored."""
    data = load_fixture("geocoding_valid.json")
    response = GeocodingResponse.model_validate(data)

    assert response.results is not None
    assert len(response.results) == 1
    loc_raw = response.results[0]
    assert loc_raw.name == "Naga"
    assert loc_raw.country == "Philippines"
    assert loc_raw.latitude == 13.61917
    assert loc_raw.longitude == 123.18139
    assert loc_raw.timezone == "Asia/Manila"

    domain_loc = map_geocoding_to_location(loc_raw)
    assert domain_loc.name == "Naga"
    assert domain_loc.country == "Philippines"
    assert domain_loc.display_name == "Naga, Bicol Region, Philippines"


def test_geocoding_no_results_and_empty_results() -> None:
    """Test geocoding response when no results key is present or results is empty."""
    no_results_data = load_fixture("geocoding_no_results.json")
    resp1 = GeocodingResponse.model_validate(no_results_data)
    assert resp1.results is None

    empty_data = load_fixture("geocoding_empty_results.json")
    resp2 = GeocodingResponse.model_validate(empty_data)
    assert resp2.results == []


def test_forecast_valid_payload_mapping() -> None:
    """Test parsing full forecast payload and mapping to Dashboard domain model."""
    data = load_fixture("forecast_valid.json")
    response = ForecastResponse.model_validate(data)

    loc = Location(
        name="Naga",
        latitude=13.62,
        longitude=123.18,
        country="Philippines",
        admin1="Bicol Region",
        timezone="Asia/Manila",
    )
    dashboard = map_forecast_to_dashboard(loc, response)

    assert dashboard.location.name == "Naga"
    assert dashboard.timezone == "Asia/Manila"
    assert dashboard.current.temperature == 29.4
    assert dashboard.current.temperature_unit == "°C"
    assert dashboard.current.apparent_temperature == 34.6
    assert dashboard.current.humidity == 76
    assert dashboard.current.wind_speed == 14.2
    assert dashboard.current.wind_speed_unit == "km/h"
    assert dashboard.current.weather_code == 51
    assert dashboard.current.weather_description == "Drizzle: Light"

    assert len(dashboard.daily) == 3
    day1 = dashboard.daily[0]
    assert day1.date == "2026-10-08"
    assert day1.temp_max == 29.5
    assert day1.temp_min == 24.9
    assert day1.precipitation_probability == 100
    assert day1.weather_description == "Thunderstorm: Slight or moderate"

    day3 = dashboard.daily[2]
    assert day3.weather_code == 95
    assert day3.weather_description == "Thunderstorm: Slight or moderate"
    assert day3.precipitation_probability == 100


def test_forecast_partial_nulls_mapping() -> None:
    """Test that nullable values and unknown WMO codes map cleanly without error."""
    data = load_fixture("forecast_partial_nulls.json")
    response = ForecastResponse.model_validate(data)

    loc = Location(
        name="Naga",
        latitude=13.62,
        longitude=123.18,
        country="Philippines",
        admin1="Bicol Region",
    )
    dashboard = map_forecast_to_dashboard(loc, response)

    assert dashboard.current.temperature is None
    assert dashboard.current.weather_code is None
    assert dashboard.current.weather_description == "Unknown"

    assert len(dashboard.daily) == 2
    day1 = dashboard.daily[0]
    assert day1.temp_max is None
    assert day1.precipitation_probability is None
    assert day1.weather_description == "Unknown"

    day2 = dashboard.daily[1]
    assert day2.weather_code == 9999
    assert day2.weather_description == "Unknown"
    assert day2.temp_max == 30.5


def test_forecast_mismatched_arrays_raises_validation_error() -> None:
    """Test that daily forecast with mismatched array lengths fails validation."""
    data = load_fixture("forecast_mismatched_arrays.json")
    with pytest.raises(ValidationError, match="Mismatched array length"):
        ForecastResponse.model_validate(data)


def test_forecast_missing_required_fields_raises_validation_error() -> None:
    """Test that missing required fields trigger Pydantic ValidationError."""
    data = load_fixture("forecast_missing_field.json")
    with pytest.raises(ValidationError):
        ForecastResponse.model_validate(data)


def test_daily_raw_equal_array_validation_direct() -> None:
    """Directly test DailyForecastRaw array validation logic."""
    raw = DailyForecastRaw(
        time=["2026-10-08", "2026-10-09"],
        weather_code=[0, 1],
        temperature_2m_max=[30.0, 31.0],
        temperature_2m_min=[24.0, 25.0],
        precipitation_probability_max=[10, 20],
    )
    assert len(raw.time) == 2

    # Mismatched lengths
    with pytest.raises(ValidationError, match="Mismatched array length"):
        DailyForecastRaw(
            time=["2026-10-08", "2026-10-09"],
            weather_code=[0],
            temperature_2m_max=[30.0, 31.0],
            temperature_2m_min=[24.0, 25.0],
        )
