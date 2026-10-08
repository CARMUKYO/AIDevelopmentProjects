"""Command line interface for the Open-Meteo Weather Dashboard."""

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from weather_dashboard.client import OpenMeteoClient
from weather_dashboard.config import load_settings
from weather_dashboard.errors import WeatherError
from weather_dashboard.http import build_client
from weather_dashboard.render import render_dashboard
from weather_dashboard.service import WeatherService

logger = logging.getLogger("weather_dashboard")

app = typer.Typer(
    name="weather",
    help="Terminal Weather Dashboard consuming the public Open-Meteo API.",
    add_completion=False,
)


def _configure_logging(verbose: bool) -> None:
    """Configure logging format and verbosity."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    logger.setLevel(level)


@app.command()
def main(
    city: Annotated[
        str | None,
        typer.Argument(
            help="City name to retrieve weather for. Defaults to 'default_city' in config.",
            show_default=False,
        ),
    ] = None,
    days: Annotated[
        int | None,
        typer.Option(
            "--days",
            "-d",
            help="Forecast days (1 to 16).",
            show_default=False,
        ),
    ] = None,
    units: Annotated[
        str | None,
        typer.Option(
            "--units",
            "-u",
            help="Measurement units ('metric' or 'imperial').",
            show_default=False,
        ),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to TOML configuration file.",
            show_default=False,
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose debug logging.",
        ),
    ] = False,
) -> None:
    """Fetch and display real-time weather and forecast."""
    _configure_logging(verbose)
    err_console = Console(stderr=True)

    try:
        settings = load_settings(
            config_path=config,
            forecast_days=days,
            units=units,
        )

        with build_client(settings) as http_client:
            client = OpenMeteoClient(http_client, settings)
            service = WeatherService(client, settings)
            dashboard = service.get_dashboard(city=city, days=days, units=units)

        render_dashboard(dashboard)

    except WeatherError as exc:
        if verbose:
            logger.exception("Weather error details:")
        err_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=exc.exit_code) from exc
    except Exception as exc:
        if verbose:
            logger.exception("Unhandled error:")
        err_console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
