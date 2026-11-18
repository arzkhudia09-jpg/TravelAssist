from __future__ import annotations

from typing import Any


INTEGRATIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "rail_partner",
        "category": "transport",
        "name": "Authorized rail partner",
        "description": "Rail schedules, fares, availability, and status through an approved partner.",
        "features": ["schedules", "fares", "availability", "service status"],
        "documentation_url": "https://www.irctc.com/",
    },
    {
        "id": "bus_partner",
        "category": "transport",
        "name": "Authorized bus partner",
        "description": "Bus routes, schedules, fares, and availability through a contracted provider.",
        "features": ["routes", "schedules", "fares", "availability"],
        "documentation_url": None,
    },
    {
        "id": "google_maps",
        "category": "maps",
        "name": "Google Maps Platform",
        "description": "Maps, geocoding, distance, and directions subject to a valid Google Cloud account.",
        "features": ["maps", "geocoding", "directions", "distance"],
        "documentation_url": "https://developers.google.com/maps/documentation",
    },
    {
        "id": "booking_demand",
        "category": "accommodation",
        "name": "Booking.com Demand API",
        "description": "Accommodation search through the eligible partner API.",
        "features": ["properties", "published pricing", "availability when supported"],
        "documentation_url": "https://developers.booking.com/demand/docs",
    },
    {
        "id": "ai_compatible",
        "category": "ai",
        "name": "OpenAI-compatible assistant",
        "description": "Optional assistant integration using persisted application context.",
        "features": ["context-aware assistance"],
        "documentation_url": None,
    },
)

ADDONS: tuple[dict[str, Any], ...] = (
    {"id": "ai_assistant", "name": "AI travel assistant", "category": "planning"},
    {"id": "weather", "name": "Weather information", "category": "travel"},
    {"id": "currency", "name": "Currency converter", "category": "travel"},
    {"id": "advanced_planner", "name": "Advanced trip planner", "category": "planning"},
    {"id": "trip_notifications", "name": "Trip notifications", "category": "notifications"},
)


class ProviderRegistry:
    """Whitelisted adapter registry; configuration cannot execute user-supplied code."""

    def __init__(self) -> None:
        self._health_checks: dict[str, Any] = {}

    def register_health_check(self, provider_id: str, health_check: Any) -> None:
        if provider_id not in {item["id"] for item in INTEGRATIONS}:
            raise ValueError(f"Unknown integration provider: {provider_id}")
        self._health_checks[provider_id] = health_check

    def has_adapter(self, provider_id: str) -> bool:
        return provider_id in self._health_checks

    def test_connection(self, provider_id: str, credentials: dict[str, str], options: dict[str, Any]) -> None:
        health_check = self._health_checks.get(provider_id)
        if health_check is None:
            raise RuntimeError("No authorized provider adapter is installed")
        health_check(credentials, options)


provider_registry = ProviderRegistry()
