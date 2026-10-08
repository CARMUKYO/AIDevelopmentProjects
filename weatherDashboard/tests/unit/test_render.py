"""Unit tests for Rich terminal dashboard rendering."""

from weather_dashboard.models import (
    CurrentConditions,
    DailyForecastItem,
    Dashboard,
    Location,
)
from weather_dashboard.render import (
    format_metric,
    render_dashboard_to_string,
)


def test_format_metric_helper() -> None:
    """Test format_metric helper for present and null values."""
    assert format_metric(25.4, "°C") == "25.4 °C"
    assert format_metric("Clear", "") == "Clear"
    assert format_metric(None, "°C") == "—"
    assert format_metric(None, "", placeholder="N/A") == "N/A"


def test_render_dashboard_snapshot_complete() -> None:
    """Test full rendering snapshot containing location, current metrics, and daily table."""
    loc = Location(
        name="Naga",
        latitude=13.62,
        longitude=123.18,
        country="Philippines",
        admin1="Bicol Region",
        timezone="Asia/Manila",
    )
    current = CurrentConditions(
        time="2026-10-08T09:00",
        temperature=29.4,
        temperature_unit="°C",
        apparent_temperature=34.6,
        humidity=76,
        wind_speed=14.2,
        wind_speed_unit="km/h",
        weather_code=51,
        weather_description="Drizzle: Light",
    )
    daily = [
        DailyForecastItem(
            date="2026-10-08",
            weather_code=95,
            weather_description="Thunderstorm: Slight or moderate",
            temp_max=29.5,
            temp_min=24.9,
            temp_unit="°C",
            precipitation_probability=100,
        ),
        DailyForecastItem(
            date="2026-10-09",
            weather_code=80,
            weather_description="Rain showers: Slight",
            temp_max=30.0,
            temp_min=24.2,
            temp_unit="°C",
            precipitation_probability=90,
        ),
    ]
    dashboard = Dashboard(
        location=loc,
        current=current,
        daily=daily,
        timezone="Asia/Manila",
        local_time="2026-10-08T09:00",
    )

    output = render_dashboard_to_string(dashboard, width=90)

    # Assert header elements
    assert "Naga, Bicol Region, Philippines" in output
    assert "13.62°" in output
    assert "123.18°" in output
    assert "2026-10-08T09:00 (Asia/Manila)" in output

    # Assert current condition metrics
    assert "Current Conditions" in output
    assert "Drizzle: Light" in output
    assert "29.4 °C" in output
    assert "34.6 °C" in output
    assert "76%" in output
    assert "14.2 km/h" in output

    # Assert daily forecast rows
    assert "Daily Forecast" in output
    assert "2026-10-08" in output
    assert "29.5 °C" in output
    assert "24.9 °C" in output
    assert "100%" in output
    assert "Thunderstorm: Slight or moderate" in output


def test_render_dashboard_with_null_and_unknown_metrics() -> None:
    """Test that null values render as '—' and unknown WMO codes display as 'Unknown'."""
    loc = Location(
        name="Naga",
        latitude=13.62,
        longitude=123.18,
        country="Philippines",
        admin1="Bicol Region",
    )
    current = CurrentConditions(
        time="2026-10-08T09:00",
        temperature=None,
        temperature_unit="°C",
        apparent_temperature=None,
        humidity=None,
        wind_speed=None,
        wind_speed_unit="km/h",
        weather_code=None,
        weather_description="Unknown",
    )
    daily = [
        DailyForecastItem(
            date="2026-10-08",
            weather_code=None,
            weather_description="Unknown",
            temp_max=None,
            temp_min=None,
            temp_unit="°C",
            precipitation_probability=None,
        ),
    ]
    dashboard = Dashboard(
        location=loc,
        current=current,
        daily=daily,
        timezone="Asia/Manila",
        local_time="2026-10-08T09:00",
    )

    output = render_dashboard_to_string(dashboard, width=90)

    assert "Unknown" in output
    assert "—" in output
    # Ensure no None appears as text
    assert "None" not in output
