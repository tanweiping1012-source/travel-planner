"""Real-data workflow primitives used by the travel planning skill."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .amap import AmapClient, AmapError
from .models import to_dict


def collect_amap_snapshot(request: Dict[str, Any], client: AmapClient) -> dict:
    """Resolve locations, routes, and nearby POIs from live Amap data."""

    origin_text = str(request["origin"])
    destination_text = str(request["destination"])
    origin_city = request.get("origin_city")
    destination_city = request.get("destination_city") or destination_text

    origin = client.resolve_location(origin_text, city=origin_city)
    destination = client.resolve_location(destination_text, city=destination_city)

    route_modes = request.get("route_modes") or ["transit", "driving"]
    routes = []
    route_errors = []
    for mode in route_modes:
        try:
            routes.append(
                client.route(
                    origin,
                    destination,
                    mode=str(mode),
                    city=destination_city,
                )
            )
        except (AmapError, ValueError) as exc:
            route_errors.append({"mode": mode, "message": str(exc)})

    discovery = request.get("discovery") or {}
    places = client.search_around(
        destination,
        keywords=discovery.get("keyword"),
        types=str(discovery.get("types") or "110000|140000"),
        radius_meters=int(discovery.get("radius_meters") or 10000),
        limit=int(discovery.get("limit") or 15),
    )

    return {
        "request": request,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "locations": {
            "origin": to_dict(origin),
            "destination": to_dict(destination),
        },
        "routes": [to_dict(route) for route in routes],
        "route_errors": route_errors,
        "nearby_places": [to_dict(place) for place in places],
        "provenance": {
            "provider": "amap",
            "live_data": True,
            "note": "Dynamic durations and availability must be refreshed before use.",
        },
    }
