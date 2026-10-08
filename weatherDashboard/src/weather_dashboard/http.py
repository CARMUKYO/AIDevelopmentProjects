"""HTTP client builder and helpers for Weather Dashboard."""

from collections.abc import Callable

import httpx

from weather_dashboard.config import Settings

SleepCallable = Callable[[float], None]


def build_client(settings: Settings) -> httpx.Client:
    """Build and configure a reusable sync httpx.Client from settings.

    Configures explicit connect and read timeouts, pool limits, and default User-Agent header.
    """
    timeout = httpx.Timeout(
        connect=settings.connect_timeout,
        read=settings.read_timeout,
        write=settings.connect_timeout,
        pool=settings.connect_timeout,
    )
    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "application/json",
    }
    return httpx.Client(timeout=timeout, headers=headers)
