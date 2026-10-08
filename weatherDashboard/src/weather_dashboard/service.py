"""Weather dashboard service orchestrator.

Coordinates geocoding and forecast retrieval to construct domain Dashboard objects.
"""

from weather_dashboard.client import OpenMeteoClient
from weather_dashboard.config import Settings
from weather_dashboard.errors import ConfigError
from weather_dashboard.models import Dashboard, map_forecast_to_dashboard


class WeatherService:
    """Orchestrates geocoding and forecasting workflows."""

    def __init__(self, client: OpenMeteoClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def get_dashboard(
        self,
        city: str | None = None,
        days: int | None = None,
        units: str | None = None,
    ) -> Dashboard:
        """Fetch geocoding and forecast data and construct a domain Dashboard model.

        Args:
            city: Target city name. If None, uses settings.default_city.
            days: Forecast duration in days (1-16). If None, uses settings.forecast_days.
            units: 'metric' or 'imperial'. If None, uses settings.units.

        Returns:
            Dashboard: Fully populated domain model ready for rendering.

        Raises:
            ConfigError: If no city is specified and no default_city is configured.
            LocationNotFound: If the city cannot be geocoded.
            ApiTimeout: If requests time out.
            ApiUnavailable: If the API is unreachable.
            ApiRequestError: On client HTTP error codes.
            UnexpectedResponse: On malformed or non-compliant payloads.
        """
        resolved_city = city or self.settings.default_city
        if not resolved_city or not resolved_city.strip():
            raise ConfigError("No city specified and no default_city configured in settings.")

        target_city = resolved_city.strip()

        # Step 1: Geocode city into domain Location
        location = self.client.geocode(target_city)

        # Step 2: Fetch forecast using coordinates
        forecast_days = days if days is not None else self.settings.forecast_days
        forecast_units = units if units is not None else self.settings.units

        forecast_resp = self.client.forecast(
            latitude=location.latitude,
            longitude=location.longitude,
            days=forecast_days,
            units=forecast_units,
        )

        # Step 3: Map to domain Dashboard
        return map_forecast_to_dashboard(location, forecast_resp)
