"""Live smoke tests querying the real Open-Meteo API (opt-in).

These tests require an active internet connection and are skipped by default.
Run explicitly with:
    uv run pytest -m live
"""

import pytest

from weather_dashboard.client import OpenMeteoClient
from weather_dashboard.config import Settings
from weather_dashboard.http import build_client
from weather_dashboard.service import WeatherService


@pytest.mark.live
def test_live_open_meteo_naga_smoke() -> None:
    """Smoke test querying real Open-Meteo Geocoding and Forecast endpoints for Naga."""
    settings = Settings(forecast_days=3, units="metric")

    with build_client(settings) as http_client:
        client = OpenMeteoClient(http_client, settings)
        service = WeatherService(client, settings)
        dashboard = service.get_dashboard(city="Naga", days=3, units="metric")

    # Assert valid geocoded location
    assert dashboard.location.name == "Naga"
    assert dashboard.location.country == "Philippines"
    assert round(dashboard.location.latitude) == 14
    assert round(dashboard.location.longitude) == 123
    assert "Asia/Manila" in dashboard.timezone

    # Assert current conditions are populated
    assert dashboard.current.temperature is not None
    assert dashboard.current.temperature_unit == "°C"
    assert dashboard.current.weather_description != ""

    # Assert daily forecasts are returned
    assert len(dashboard.daily) == 3
    for day in dashboard.daily:
        assert day.date != ""
        assert day.temp_max is not None
        assert day.temp_min is not None
