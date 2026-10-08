"""Unit tests for WeatherService orchestration."""

from unittest.mock import MagicMock

import pytest

from weather_dashboard.client import OpenMeteoClient
from weather_dashboard.config import Settings
from weather_dashboard.errors import ConfigError
from weather_dashboard.models import (
    CurrentUnitsRaw,
    CurrentWeatherRaw,
    DailyForecastRaw,
    DailyUnitsRaw,
    ForecastResponse,
    Location,
)
from weather_dashboard.service import WeatherService


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock OpenMeteoClient."""
    client = MagicMock(spec=OpenMeteoClient)
    client.geocode.return_value = Location(
        name="Naga",
        latitude=13.62,
        longitude=123.18,
        country="Philippines",
        admin1="Bicol Region",
        timezone="Asia/Manila",
    )
    client.forecast.return_value = ForecastResponse(
        latitude=13.62,
        longitude=123.18,
        timezone="Asia/Manila",
        current=CurrentWeatherRaw(
            time="2026-10-08T09:00",
            temperature_2m=29.4,
            relative_humidity_2m=76,
            apparent_temperature=34.6,
            weather_code=51,
            wind_speed_10m=14.2,
        ),
        current_units=CurrentUnitsRaw(
            temperature_2m="°C",
            wind_speed_10m="km/h",
        ),
        daily=DailyForecastRaw(
            time=["2026-10-08"],
            weather_code=[95],
            temperature_2m_max=[29.5],
            temperature_2m_min=[24.9],
            precipitation_probability_max=[100],
        ),
        daily_units=DailyUnitsRaw(
            temperature_2m_max="°C",
            temperature_2m_min="°C",
        ),
    )
    return client


def test_service_orchestration_happy_path(mock_client: MagicMock) -> None:
    """Test standard service orchestration from city name to domain Dashboard."""
    settings = Settings(default_city=None, forecast_days=3, units="metric")
    service = WeatherService(mock_client, settings)

    dashboard = service.get_dashboard(city="Naga", days=3, units="metric")

    mock_client.geocode.assert_called_once_with("Naga")
    mock_client.forecast.assert_called_once_with(
        latitude=13.62,
        longitude=123.18,
        days=3,
        units="metric",
    )
    assert dashboard.location.name == "Naga"
    assert dashboard.current.temperature == 29.4
    assert len(dashboard.daily) == 1
    assert dashboard.daily[0].temp_max == 29.5


def test_service_uses_default_city_when_none_provided(mock_client: MagicMock) -> None:
    """Test that default_city from settings is used when no city is passed."""
    settings = Settings(default_city="Naga", forecast_days=7, units="metric")
    service = WeatherService(mock_client, settings)

    dashboard = service.get_dashboard(city=None)

    mock_client.geocode.assert_called_once_with("Naga")
    assert dashboard.location.name == "Naga"


def test_service_raises_config_error_when_no_city_and_no_default(mock_client: MagicMock) -> None:
    """Test that ConfigError is raised if neither city nor default_city is provided."""
    settings = Settings(default_city=None)
    service = WeatherService(mock_client, settings)

    with pytest.raises(ConfigError, match="No city specified and no default_city configured"):
        service.get_dashboard(city=None)

    mock_client.geocode.assert_not_called()
    mock_client.forecast.assert_not_called()
