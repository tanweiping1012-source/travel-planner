"""Read-only connector for the official Amap Web Service API."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .geomatch import assess_geocode, coverage_hint
from .models import Location, Place, Route, Source


class AmapError(RuntimeError):
    """Provider error that intentionally excludes request URLs and credentials."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any, default: float = 0) -> float:
    if value in (None, "", []):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _minutes(seconds: Any) -> int:
    return max(0, math.ceil(_number(seconds) / 60))


class AmapClient:
    BASE_URL = "https://restapi.amap.com"

    def __init__(
        self,
        api_key: str,
        timeout_seconds: int = 15,
        transport: Optional[Callable[[str, Dict[str, str]], Dict[str, Any]]] = None,
    ):
        if not api_key.strip():
            raise ValueError("Amap API key cannot be empty")
        self._api_key = api_key.strip()
        self._timeout_seconds = timeout_seconds
        self._transport = transport or self._http_get

    def _http_get(self, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        query = urllib.parse.urlencode({**params, "key": self._api_key})
        request = urllib.request.Request(
            f"{self.BASE_URL}{path}?{query}",
            headers={"User-Agent": "travel-planner-mvp/0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AmapError("Amap request failed due to a network error") from exc

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise AmapError("Amap returned an invalid JSON response") from exc
        return data

    def _get(self, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        data = self._transport(path, params)
        if str(data.get("status")) != "1":
            info = str(data.get("info") or "UNKNOWN_ERROR")
            infocode = str(data.get("infocode") or "unknown")
            raise AmapError(f"Amap rejected the request: {info} ({infocode})")
        return data

    def preflight(self) -> dict:
        places = self.search_places("天安门", city="北京", limit=1)
        return {
            "provider": "amap",
            "status": "READY" if places else "DEGRADED",
            "result_count": len(places),
            "checked_at": _now(),
        }

    def geocode(
        self,
        address: str,
        city: Optional[str] = None,
        *,
        expect_settlement: bool = False,
        allow_low_confidence: bool = False,
    ) -> Location:
        params = {"address": address}
        if city:
            params["city"] = city
        data = self._get("/v3/geocode/geo", params)
        geocodes = data.get("geocodes") or []
        if not geocodes:
            raise AmapError(f"Amap could not resolve location: {address}")
        item = geocodes[0]
        assessment = assess_geocode(
            address,
            item.get("formatted_address"),
            level=item.get("level"),
            candidate_count=len(geocodes),
            expect_settlement=expect_settlement,
        )
        if assessment["confidence"] == "LOW" and not allow_low_confidence:
            # Returning these coordinates would be worse than returning
            # nothing: they look verified and are not.
            raise AmapError(
                f"Amap 未能可靠定位「{address}」："
                + "；".join(assessment["reasons"])
                + "。"
                + (coverage_hint(assessment) or "")
            )
        longitude, latitude = self._parse_coordinates(item.get("location"))
        return Location(
            name=item.get("formatted_address") or address,
            longitude=longitude,
            latitude=latitude,
            city=item.get("city") or city,
            match=assessment,
        )

    def resolve_location(
        self,
        query: str,
        city: Optional[str] = None,
        *,
        expect_settlement: bool = False,
    ) -> Location:
        """Prefer a named POI and fall back to address geocoding.

        The POI-preference branch below is what let a search for the city
        "东京" resolve to a Beijing restaurant coincidentally named 东京: a
        keyword match against ``search_places`` requires no settlement-level
        check at all, so it silently bypassed the Coverage Gate refusal that
        ``geocode(expect_settlement=True)`` provides. A trip's origin and
        destination are settlements, not venues, so ``expect_settlement=True``
        skips this branch entirely and defers straight to ``geocode``, which
        does the real check.
        """

        if expect_settlement:
            return self.geocode(query, city=city, expect_settlement=True)

        places = self.search_places(query, city=city, limit=10)
        if places:
            available = [
                place
                for place in places
                if not any(
                    marker in place.name
                    for marker in ("暂停开放", "临时关闭", "已关闭", "停止营业")
                )
            ]
            candidates = available or places

            def score(place: Place) -> tuple:
                return (
                    int(place.name == query),
                    int(query in place.name or place.name in query),
                    int(bool(place.category and "风景名胜" in place.category)),
                    place.rating or 0,
                )

            return max(candidates, key=score).location
        return self.geocode(query, city=city)

    def search_places(
        self, keywords: str, city: Optional[str] = None, limit: int = 10
    ) -> List[Place]:
        params = {
            "keywords": keywords,
            "offset": str(min(max(limit, 1), 25)),
            "page": "1",
            "extensions": "all",
        }
        if city:
            params.update({"city": city, "citylimit": "true"})
        data = self._get("/v3/place/text", params)
        return self._normalize_places(data.get("pois") or [])

    def search_around(
        self,
        center: Location,
        keywords: Optional[str] = None,
        types: str = "110000|140000",
        radius_meters: int = 10000,
        limit: int = 20,
    ) -> List[Place]:
        params = {
            "location": center.coordinates,
            "radius": str(min(max(radius_meters, 100), 50000)),
            "types": types,
            "sortrule": "weight",
            "offset": str(min(max(limit, 1), 25)),
            "page": "1",
            "extensions": "all",
        }
        if keywords:
            params["keywords"] = keywords
        data = self._get("/v3/place/around", params)
        return self._normalize_places(data.get("pois") or [])

    def route(
        self,
        origin: Location,
        destination: Location,
        mode: str,
        city: Optional[str] = None,
    ) -> Route:
        mode = mode.lower()
        common = {
            "origin": origin.coordinates,
            "destination": destination.coordinates,
        }
        if mode == "walking":
            data = self._get("/v3/direction/walking", common)
            return self._normalize_simple_route(data, mode, origin, destination)
        if mode == "driving":
            data = self._get("/v3/direction/driving", common)
            return self._normalize_simple_route(data, mode, origin, destination)
        if mode == "transit":
            transit_params = {
                **common,
                "city": origin.city or city or "",
                "cityd": destination.city or city or "",
            }
            data = self._get("/v3/direction/transit/integrated", transit_params)
            return self._normalize_transit_route(data, origin, destination)
        raise ValueError("Route mode must be walking, driving, or transit")

    def _normalize_places(self, items: List[Dict[str, Any]]) -> List[Place]:
        checked_at = _now()
        places = []
        for item in items:
            try:
                longitude, latitude = self._parse_coordinates(item.get("location"))
            except AmapError:
                continue
            business = item.get("biz_ext") if isinstance(item.get("biz_ext"), dict) else {}
            rating = _number(business.get("rating"), default=-1)
            city = item.get("cityname")
            places.append(
                Place(
                    name=str(item.get("name") or ""),
                    location=Location(
                        name=str(item.get("name") or ""),
                        longitude=longitude,
                        latitude=latitude,
                        city=city if isinstance(city, str) else None,
                    ),
                    address=self._string_or_none(item.get("address")),
                    category=self._string_or_none(item.get("type")),
                    rating=rating if rating >= 0 else None,
                    source=Source(
                        provider="amap",
                        checked_at=checked_at,
                        provider_id=self._string_or_none(item.get("id")),
                    ),
                )
            )
        return places

    def _normalize_simple_route(
        self,
        data: Dict[str, Any],
        mode: str,
        origin: Location,
        destination: Location,
    ) -> Route:
        paths = (data.get("route") or {}).get("paths") or []
        if not paths:
            raise AmapError(f"Amap returned no {mode} route")
        path = paths[0]
        return Route(
            mode=mode,
            origin=origin,
            destination=destination,
            duration_minutes=_minutes(path.get("duration")),
            distance_meters=int(_number(path.get("distance"))),
            walking_distance_meters=(
                int(_number(path.get("distance"))) if mode == "walking" else 0
            ),
            estimated_cost=_number(path.get("tolls"), default=0) if mode == "driving" else None,
            source=Source(provider="amap", checked_at=_now()),
        )

    def _normalize_transit_route(
        self, data: Dict[str, Any], origin: Location, destination: Location
    ) -> Route:
        route_data = data.get("route") or {}
        transits = route_data.get("transits") or []
        if not transits:
            raise AmapError("Amap returned no transit route")
        transit = transits[0]
        segments = transit.get("segments") or []
        transfer_count = max(
            0,
            sum(1 for segment in segments if (segment.get("bus") or {}).get("buslines")) - 1,
        )
        return Route(
            mode="transit",
            origin=origin,
            destination=destination,
            duration_minutes=_minutes(transit.get("duration")),
            distance_meters=int(_number(transit.get("distance"))),
            transfer_count=transfer_count,
            walking_distance_meters=int(_number(transit.get("walking_distance"))),
            estimated_cost=_number(transit.get("cost"), default=0),
            source=Source(provider="amap", checked_at=_now()),
        )

    @staticmethod
    def _parse_coordinates(value: Any) -> tuple:
        if not isinstance(value, str) or "," not in value:
            raise AmapError("Amap returned a place without valid coordinates")
        longitude, latitude = value.split(",", 1)
        return float(longitude), float(latitude)

    @staticmethod
    def _string_or_none(value: Any) -> Optional[str]:
        return value if isinstance(value, str) and value else None
