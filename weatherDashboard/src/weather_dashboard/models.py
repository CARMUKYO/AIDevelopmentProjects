"""Data models for Weather Dashboard.

Separates raw API response models (Pydantic v2) from clean domain models
(dataclasses) used by orchestration and rendering.
"""

from dataclasses import dataclass
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --- WMO Weather Code Mapping ---

WMO_CODE_MAP: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Drizzle: Light",
    53: "Drizzle: Moderate",
    55: "Drizzle: Dense intensity",
    56: "Freezing Drizzle: Light",
    57: "Freezing Drizzle: Dense intensity",
    61: "Rain: Slight",
    63: "Rain: Moderate",
    65: "Rain: Heavy intensity",
    66: "Freezing Rain: Light",
    67: "Freezing Rain: Heavy intensity",
    71: "Snow fall: Slight",
    73: "Snow fall: Moderate",
    75: "Snow fall: Heavy intensity",
    77: "Snow grains",
    80: "Rain showers: Slight",
    81: "Rain showers: Moderate",
    82: "Rain showers: Violent",
    85: "Snow showers: Slight",
    86: "Snow showers: Heavy",
    95: "Thunderstorm: Slight or moderate",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def get_wmo_description(code: int | None) -> str:
    """Map a WMO weather code to a human-readable description.

    Unknown codes or None safely map to 'Unknown'.
    """
    if code is None:
        return "Unknown"
    return WMO_CODE_MAP.get(code, "Unknown")


# --- Raw API Response Models (Pydantic v2) ---


class GeocodingLocationRaw(BaseModel):
    """Single geocoding search result from Open-Meteo."""

    id: int | None = None
    name: str
    latitude: float
    longitude: float
    elevation: float | None = None
    feature_code: str | None = None
    country_code: str | None = None
    country: str | None = None
    admin1: str | None = None
    timezone: str | None = None

    model_config = ConfigDict(extra="ignore")


class GeocodingResponse(BaseModel):
    """Raw response from Open-Meteo Geocoding API."""

    results: list[GeocodingLocationRaw] | None = None
    generationtime_ms: float | None = None

    model_config = ConfigDict(extra="ignore")


class CurrentUnitsRaw(BaseModel):
    """Units for current weather metrics."""

    time: str | None = None
    interval: str | None = None
    temperature_2m: str = "°C"
    relative_humidity_2m: str = "%"
    apparent_temperature: str = "°C"
    weather_code: str | None = None
    wind_speed_10m: str = "km/h"

    model_config = ConfigDict(extra="ignore")


class CurrentWeatherRaw(BaseModel):
    """Raw current weather readings."""

    time: str
    interval: int | None = None
    temperature_2m: float | None = None
    relative_humidity_2m: float | int | None = None
    apparent_temperature: float | None = None
    weather_code: int | None = None
    wind_speed_10m: float | None = None

    model_config = ConfigDict(extra="ignore")


class DailyUnitsRaw(BaseModel):
    """Units for daily forecast metrics."""

    time: str | None = None
    weather_code: str | None = None
    temperature_2m_max: str = "°C"
    temperature_2m_min: str = "°C"
    precipitation_probability_max: str = "%"

    model_config = ConfigDict(extra="ignore")


class DailyForecastRaw(BaseModel):
    """Raw daily forecast metrics containing parallel arrays."""

    time: list[str]
    weather_code: list[int | None]
    temperature_2m_max: list[float | None]
    temperature_2m_min: list[float | None]
    precipitation_probability_max: list[float | int | None] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def validate_array_lengths(self) -> Self:
        """Ensure all daily forecast arrays are equal in length."""
        expected_len = len(self.time)
        arrays: dict[str, list[int | None] | list[float | None] | list[float | int | None]] = {
            "weather_code": self.weather_code,
            "temperature_2m_max": self.temperature_2m_max,
            "temperature_2m_min": self.temperature_2m_min,
        }
        if self.precipitation_probability_max:
            arrays["precipitation_probability_max"] = self.precipitation_probability_max

        for name, arr in arrays.items():
            if len(arr) != expected_len:
                raise ValueError(
                    f"Mismatched array length for '{name}': expected {expected_len}, got {len(arr)}"
                )
        return self


class ForecastResponse(BaseModel):
    """Raw response from Open-Meteo Forecast API."""

    latitude: float
    longitude: float
    timezone: str
    timezone_abbreviation: str | None = None
    utc_offset_seconds: int | None = None
    elevation: float | None = None
    generationtime_ms: float | None = None
    current: CurrentWeatherRaw
    current_units: CurrentUnitsRaw = Field(default_factory=CurrentUnitsRaw)
    daily: DailyForecastRaw
    daily_units: DailyUnitsRaw = Field(default_factory=DailyUnitsRaw)

    model_config = ConfigDict(extra="ignore")


class ApiErrorPayload(BaseModel):
    """Open-Meteo error payload returned on 400 responses."""

    error: bool = False
    reason: str | None = None

    model_config = ConfigDict(extra="ignore")


# --- Domain Models (Clean Dataclasses) ---


@dataclass(frozen=True)
class Location:
    """Domain model representing a geocoded location."""

    name: str
    latitude: float
    longitude: float
    country: str | None = None
    admin1: str | None = None
    timezone: str | None = None

    @property
    def display_name(self) -> str:
        """Formatted display name e.g. 'Manila, Metro Manila, Philippines'."""
        parts: list[str] = [self.name]
        if self.admin1 and self.admin1.lower() != self.name.lower():
            parts.append(self.admin1)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)


@dataclass(frozen=True)
class CurrentConditions:
    """Domain model for current weather conditions."""

    time: str
    temperature: float | None
    temperature_unit: str
    apparent_temperature: float | None
    humidity: float | int | None
    wind_speed: float | None
    wind_speed_unit: str
    weather_code: int | None
    weather_description: str


@dataclass(frozen=True)
class DailyForecastItem:
    """Domain model for a single day's forecast."""

    date: str
    weather_code: int | None
    weather_description: str
    temp_max: float | None
    temp_min: float | None
    temp_unit: str
    precipitation_probability: float | int | None


@dataclass(frozen=True)
class Dashboard:
    """Aggregated domain model ready for UI rendering."""

    location: Location
    current: CurrentConditions
    daily: list[DailyForecastItem]
    timezone: str
    local_time: str


# --- Mapping Helpers ---


def map_geocoding_to_location(raw: GeocodingLocationRaw) -> Location:
    """Convert raw geocoding location to domain Location."""
    return Location(
        name=raw.name,
        latitude=raw.latitude,
        longitude=raw.longitude,
        country=raw.country,
        admin1=raw.admin1,
        timezone=raw.timezone,
    )


def map_forecast_to_dashboard(location: Location, raw: ForecastResponse) -> Dashboard:
    """Convert raw forecast response and location to domain Dashboard model."""
    current_u = raw.current_units
    daily_u = raw.daily_units

    current = CurrentConditions(
        time=raw.current.time,
        temperature=raw.current.temperature_2m,
        temperature_unit=current_u.temperature_2m,
        apparent_temperature=raw.current.apparent_temperature,
        humidity=raw.current.relative_humidity_2m,
        wind_speed=raw.current.wind_speed_10m,
        wind_speed_unit=current_u.wind_speed_10m,
        weather_code=raw.current.weather_code,
        weather_description=get_wmo_description(raw.current.weather_code),
    )

    precip_list = raw.daily.precipitation_probability_max or [None] * len(raw.daily.time)
    daily_items: list[DailyForecastItem] = []
    for i, date_str in enumerate(raw.daily.time):
        precip = precip_list[i] if i < len(precip_list) else None
        daily_items.append(
            DailyForecastItem(
                date=date_str,
                weather_code=raw.daily.weather_code[i],
                weather_description=get_wmo_description(raw.daily.weather_code[i]),
                temp_max=raw.daily.temperature_2m_max[i],
                temp_min=raw.daily.temperature_2m_min[i],
                temp_unit=daily_u.temperature_2m_max,
                precipitation_probability=precip,
            )
        )

    return Dashboard(
        location=location,
        current=current,
        daily=daily_items,
        timezone=raw.timezone,
        local_time=raw.current.time,
    )
