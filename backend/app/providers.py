from .config import settings


class ProviderUnavailable(Exception):
    pass


class TransportProvider:
    name = "unconfigured"

    def search(self, source: str, destination: str, departure_date: str | None):
        raise ProviderUnavailable("No authorized transport provider is configured")


class StayProvider:
    name = "unconfigured"

    def search(self, destination: str, max_price: float | None):
        raise ProviderUnavailable("No authorized accommodation provider is configured")


def search_transport(source: str, destination: str, departure_date: str | None):
    if not settings.demo_mode:
        return TransportProvider().search(source, destination, departure_date)
    return {
        "data_status": "demo",
        "provider": "synthetic-development-fixture",
        "is_bookable": False,
        "notice": "Synthetic example only. Not a real service, schedule, fare, or availability.",
        "routes": [
            {
                "id": "demo-route-1",
                "source": source,
                "destination": destination,
                "mode": "train",
                "service": "DEMO ONLY",
                "stops": [source, "Example interchange (demo)", destination],
                "departure": "08:00 (demo)",
                "arrival": "14:00 (demo)",
                "duration_minutes": 360,
                "transfers": 1,
                "fare_inr": 999.0,
                "reliability": None,
                "data_status": "demo",
                "is_bookable": False,
            }
        ],
        "recommendations": {"cheapest": "demo-route-1", "fastest": "demo-route-1", "balanced": "demo-route-1"},
    }


def search_stays(destination: str, max_price: float | None):
    if not settings.demo_mode:
        return StayProvider().search(destination, max_price)
    return {
        "data_status": "demo",
        "provider": "synthetic-development-fixture",
        "is_bookable": False,
        "notice": "Synthetic example only. Not a real property, price, rating, or availability.",
        "stays": [
            {
                "name": "Demo guest house (not a real listing)",
                "destination": destination,
                "price_inr": 500.0,
                "facilities": ["demo data"],
                "distance_km": None,
                "rating": None,
                "availability": "unknown",
                "data_status": "demo",
                "is_bookable": False,
            }
        ] if max_price is None or max_price >= 500 else [],
    }


def rank_routes(result: dict, budget: float | None, preference: str = "balanced") -> dict:
    routes = result.get("routes", [])
    for route in routes:
        fare = route.get("fare_inr")
        route["budget_status"] = (
            "unknown" if fare is None or budget is None
            else "within_budget" if fare <= budget
            else "over_budget"
        )
    candidates = [
        route for route in routes
        if route.get("fare_inr") is not None
        and route.get("duration_minutes") is not None
        and (budget is None or route["fare_inr"] <= budget)
    ]
    cheapest = min(candidates, key=lambda route: route["fare_inr"], default=None)
    fastest = min(candidates, key=lambda route: route["duration_minutes"], default=None)
    balanced = None
    if candidates:
        fares = [route["fare_inr"] for route in candidates]
        durations = [route["duration_minutes"] for route in candidates]
        fare_range = max(fares) - min(fares) or 1
        duration_range = max(durations) - min(durations) or 1
        balanced = min(
            candidates,
            key=lambda route: (route["fare_inr"] - min(fares)) / fare_range
            + (route["duration_minutes"] - min(durations)) / duration_range,
        )
    result["recommendations"] = {
        "cheapest": cheapest.get("id") if cheapest else None,
        "fastest": fastest.get("id") if fastest else None,
        "balanced": balanced.get("id") if balanced else None,
    }
    result["preferred_option"] = result["recommendations"].get(preference)
    return result
