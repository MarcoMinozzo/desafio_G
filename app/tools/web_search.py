"""General lookup for weather and the euro rate. Never a Getnet source."""

from __future__ import annotations

from typing import Protocol

import httpx

PORTO_ALEGRE = (-30.0346, -51.2177)


class WebSearch(Protocol):
    def lookup(self, kind: str, message: str) -> str | None:
        """Return a public fact, or None when the lookup is unavailable."""


class FakeWebSearch:
    def lookup(self, kind: str, message: str) -> str | None:
        if kind == "weather":
            return (
                "Porto Alegre tomorrow: mild weather, high near 22 C. "
                "This is a general public lookup, not Getnet product material."
            )
        if kind == "fx":
            return (
                "Euro exchange rate today: 1 EUR is about 6.10 BRL in this demo lookup. "
                "This is a general public lookup, not Getnet product material."
            )
        return None


class HttpWebSearch:
    def lookup(self, kind: str, message: str) -> str | None:
        try:
            if kind == "weather":
                return _weather()
            if kind == "fx":
                return _euro_rate()
        except httpx.HTTPError:
            return None
        return None


def _weather() -> str:
    latitude, longitude = PORTO_ALEGRE
    response = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": "America/Sao_Paulo",
            "forecast_days": 2,
        },
        timeout=8.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    daily = response.json()["daily"]
    day = daily["time"][1]
    high = daily["temperature_2m_max"][1]
    low = daily["temperature_2m_min"][1]
    return (
        f"Porto Alegre on {day}: low {low} C, high {high} C. "
        "This is a general public lookup, not Getnet product material."
    )


def _euro_rate() -> str:
    response = httpx.get(
        "https://api.frankfurter.app/latest",
        params={"from": "EUR", "to": "BRL"},
        timeout=8.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    rate = response.json()["rates"]["BRL"]
    return (
        f"Euro exchange rate today: 1 EUR = {rate} BRL. "
        "This is a general public lookup, not Getnet product material."
    )
