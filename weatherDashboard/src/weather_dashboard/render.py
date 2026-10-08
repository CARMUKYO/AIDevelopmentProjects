"""Rich terminal rendering for Weather Dashboard domain models."""

import io
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from weather_dashboard.models import Dashboard


def format_metric(val: Any | None, unit: str = "", placeholder: str = "—") -> str:
    """Format an optional metric value, falling back to a placeholder for nulls."""
    if val is None:
        return placeholder
    if unit:
        return f"{val} {unit}".strip()
    return str(val)


def build_header_panel(dashboard: Dashboard) -> Panel:
    """Construct header panel showing location, coordinates, and local time."""
    loc = dashboard.location
    lat_str = f"{loc.latitude:.2f}°"
    lon_str = f"{loc.longitude:.2f}°"

    content = Text()
    content.append(f"{loc.display_name}\n", style="bold cyan")
    content.append(f"Coordinates: {lat_str}, {lon_str}  |  ", style="dim")
    content.append(
        f"Local Time: {dashboard.local_time} ({dashboard.timezone})", style="bold yellow"
    )

    return Panel(
        content,
        title="[bold blue]Open-Meteo Weather Dashboard[/bold blue]",
        border_style="blue",
        box=box.ROUNDED,
    )


def build_current_panel(dashboard: Dashboard) -> Panel:
    """Construct current weather conditions panel."""
    cur = dashboard.current

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", justify="left")
    table.add_column(style="bold", justify="left")

    table.add_row("Condition:", cur.weather_description)
    table.add_row("Temperature:", format_metric(cur.temperature, cur.temperature_unit))
    table.add_row(
        "Feels Like:",
        format_metric(cur.apparent_temperature, cur.temperature_unit),
    )
    humidity_str = f"{cur.humidity}%" if cur.humidity is not None else "—"
    table.add_row("Humidity:", humidity_str)
    table.add_row("Wind Speed:", format_metric(cur.wind_speed, cur.wind_speed_unit))

    return Panel(
        table,
        title="[bold green]Current Conditions[/bold green]",
        border_style="green",
        box=box.ROUNDED,
    )


def build_daily_table(dashboard: Dashboard) -> Table:
    """Construct daily forecast table."""
    table = Table(
        title="Daily Forecast",
        title_style="bold magenta",
        box=box.ROUNDED,
        expand=True,
    )
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Condition", style="white")
    table.add_column("Max Temp", justify="right", style="red")
    table.add_column("Min Temp", justify="right", style="blue")
    table.add_column("Precip. Prob.", justify="right", style="green")

    for item in dashboard.daily:
        max_str = format_metric(item.temp_max, item.temp_unit)
        min_str = format_metric(item.temp_min, item.temp_unit)
        precip_str = (
            f"{item.precipitation_probability}%"
            if item.precipitation_probability is not None
            else "—"
        )

        table.add_row(
            item.date,
            item.weather_description,
            max_str,
            min_str,
            precip_str,
        )

    return table


def build_dashboard_renderables(dashboard: Dashboard) -> Group:
    """Aggregate all UI sections into a single renderable group."""
    return Group(
        build_header_panel(dashboard),
        build_current_panel(dashboard),
        build_daily_table(dashboard),
    )


def render_dashboard_to_string(dashboard: Dashboard, width: int = 80) -> str:
    """Render dashboard to a string for testing and snapshot verification."""
    buf = io.StringIO()
    console = Console(file=buf, width=width, color_system=None, highlight=False)
    console.print(build_dashboard_renderables(dashboard))
    return buf.getvalue()


def render_dashboard(dashboard: Dashboard, console: Console | None = None) -> None:
    """Render the weather dashboard to the given console (or stdout)."""
    target_console = console if console is not None else Console()
    target_console.print(build_dashboard_renderables(dashboard))
