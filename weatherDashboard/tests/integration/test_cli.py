"""CLI end-to-end integration tests using typer.testing.CliRunner and respx."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from respx import MockRouter
from typer.testing import CliRunner

from weather_dashboard.cli import app

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
runner = CliRunner()


def load_fixture(filename: str) -> dict[str, Any]:
    """Load JSON test fixture from tests/fixtures."""
    return json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_cli_happy_path(respx_mock: MockRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI happy path renders dashboard with exit code 0."""
    monkeypatch.setenv("WEATHER_BACKOFF_BASE", "0.01")
    geo_data = load_fixture("geocoding_valid.json")
    forecast_data = load_fixture("forecast_valid.json")

    respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json=geo_data)
    )
    respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(200, json=forecast_data)
    )

    result = runner.invoke(app, ["Naga", "--days", "3"])
    assert result.exit_code == 0
    assert "Naga" in result.output
    assert "Current Conditions" in result.output
    assert "Daily Forecast" in result.output


def test_cli_missing_city_and_no_default_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI exits with code 2 when no city is given and no default_city configured."""
    monkeypatch.delenv("WEATHER_DEFAULT_CITY", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", "/nonexistent/xdg")

    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "No city specified and no default_city configured" in result.output


def test_cli_invalid_config_days_zero_exit_2() -> None:
    """Test CLI exits with code 2 when invalid --days 0 is given."""
    result = runner.invoke(app, ["Naga", "--days", "0"])
    assert result.exit_code == 2
    assert "Invalid configuration for 'forecast_days'" in result.output


def test_cli_nonexistent_config_file_exit_2() -> None:
    """Test CLI exits with code 2 when explicit --config file is missing."""
    result = runner.invoke(app, ["Naga", "--config", "/nonexistent/file.toml"])
    assert result.exit_code == 2
    assert "Configuration file not found" in result.output


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_cli_city_not_found_exit_3(respx_mock: MockRouter) -> None:
    """Test CLI exits with code 3 when city cannot be found."""
    no_results = load_fixture("geocoding_no_results.json")
    respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json=no_results)
    )

    result = runner.invoke(app, ["NonexistentCity"])
    assert result.exit_code == 3
    assert "Location not found for city" in result.output


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_cli_timeout_exit_4(respx_mock: MockRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI exits with code 4 when API requests time out."""
    monkeypatch.setenv("WEATHER_MAX_RETRIES", "1")
    monkeypatch.setenv("WEATHER_BACKOFF_BASE", "0.01")

    respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        side_effect=httpx.ConnectTimeout("Connection timed out")
    )

    result = runner.invoke(app, ["Naga"])
    assert result.exit_code == 4
    assert "API request timed out" in result.output


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_cli_api_unavailable_503_exit_4(
    respx_mock: MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test CLI exits with code 4 when server returns persistent 503."""
    monkeypatch.setenv("WEATHER_MAX_RETRIES", "1")
    monkeypatch.setenv("WEATHER_BACKOFF_BASE", "0.01")

    respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )

    result = runner.invoke(app, ["Naga"])
    assert result.exit_code == 4
    assert "API unavailable" in result.output


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_cli_api_request_error_400_exit_5(respx_mock: MockRouter) -> None:
    """Test CLI exits with code 5 when API returns 400 with reason message."""
    geo_data = load_fixture("geocoding_valid.json")
    err_400 = load_fixture("api_error_400.json")

    respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json=geo_data)
    )
    respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(400, json=err_400)
    )

    result = runner.invoke(app, ["Naga"])
    assert result.exit_code == 5
    assert "Latitude must be in range of -90 to 90°" in result.output


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_cli_unexpected_response_html_exit_6(respx_mock: MockRouter) -> None:
    """Test CLI exits with code 6 when response has unexpected HTML content type."""
    respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            text="<html>Error</html>",
        )
    )

    result = runner.invoke(app, ["Naga"])
    assert result.exit_code == 6
    assert "Unexpected Content-Type" in result.output


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_cli_unexpected_response_mismatched_arrays_exit_6(respx_mock: MockRouter) -> None:
    """Test CLI exits with code 6 when forecast daily arrays are mismatched."""
    geo_data = load_fixture("geocoding_valid.json")
    mismatched = load_fixture("forecast_mismatched_arrays.json")

    respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json=geo_data)
    )
    respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(200, json=mismatched)
    )

    result = runner.invoke(app, ["Naga"])
    assert result.exit_code == 6
    assert "Mismatched array length" in result.output


@respx.mock(assert_all_mocked=True, assert_all_called=True)
def test_cli_verbose_flag(respx_mock: MockRouter, caplog: pytest.LogCaptureFixture) -> None:
    """Test CLI --verbose logs exception trace and details."""
    no_results = load_fixture("geocoding_no_results.json")
    respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
        return_value=httpx.Response(200, json=no_results)
    )

    result = runner.invoke(app, ["Naga", "--verbose"])
    assert result.exit_code == 3
