"""Normalized models shared by provider connectors and the feasibility engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Source:
    provider: str
    checked_at: str
    provider_id: Optional[str] = None
    url: Optional[str] = None


@dataclass(frozen=True)
class Location:
    name: str
    longitude: float
    latitude: float
    city: Optional[str] = None
    #: How well the geocoder's answer matched the query, from
    #: :mod:`travel_planner.geomatch`. Absent for coordinates that did not
    #: come from a geocode lookup.
    match: Optional[dict] = None

    @property
    def coordinates(self) -> str:
        return f"{self.longitude},{self.latitude}"


@dataclass(frozen=True)
class Place:
    name: str
    location: Location
    address: Optional[str]
    category: Optional[str]
    rating: Optional[float]
    source: Source


@dataclass(frozen=True)
class Route:
    mode: str
    origin: Location
    destination: Location
    duration_minutes: int
    distance_meters: int
    transfer_count: int = 0
    walking_distance_meters: int = 0
    estimated_cost: Optional[float] = None
    source: Optional[Source] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    return value


JsonDict = Dict[str, Any]
JsonList = List[JsonDict]
