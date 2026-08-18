"""Normalize 12306 MCP results into itinerary activities.

The community 12306 MCP reports seat availability the way 12306 itself does:
an exact count while twenty or fewer remain, then ``有`` once supply is
comfortable and ``无`` when a class is sold out. Mixing integers and words in
one field makes the raw payload unsafe to compare or sort, so every consumer
here goes through :func:`normalize_seat`.

``query-tickets`` carries no fare, so a price must come from the separate
``query-ticket-price`` tool. Nothing in this module invents one.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional

#: Availability above which 12306 stops reporting an exact count.
EXACT_COUNT_CEILING = 20

SEAT_LABELS = {
    "business": "商务座",
    "first_class": "一等座",
    "second_class": "二等座",
    "soft_sleeper": "软卧",
    "hard_sleeper": "硬卧",
    "hard_seat": "硬座",
    "no_seat": "无座",
}

#: Seat classes ordered from most to least comfortable, used to pick a default.
SEAT_PREFERENCE = (
    "business",
    "first_class",
    "second_class",
    "soft_sleeper",
    "hard_sleeper",
    "hard_seat",
    "no_seat",
)

TRAIN_CATEGORIES = {
    "G": "高铁",
    "C": "城际",
    "D": "动车",
    "Z": "直达特快",
    "T": "特快",
    "K": "快速",
    "Y": "旅游",
}

#: Gate-closing buffer required before a train departs, matching the TRAIN
#: default in :mod:`travel_planner.feasibility`.
DEFAULT_RAIL_BUFFER_MINUTES = 45


class RailDataError(ValueError):
    """Raised when a 12306 payload cannot be interpreted."""


def parse_duration(value: Any) -> Optional[int]:
    """Convert a ``HH:MM`` journey time into minutes."""

    text = str(value or "").strip()
    if not text or ":" not in text:
        return None
    hours, _, minutes = text.partition(":")
    try:
        return int(hours) * 60 + int(minutes)
    except ValueError:
        return None


def normalize_seat(value: Any) -> Dict[str, Any]:
    """Turn one raw seat value into a comparable record.

    ``at_least`` is the useful field for ranking: ``有`` has no exact count but
    is still known to exceed :data:`EXACT_COUNT_CEILING`, so candidates stay
    sortable without inventing a number.
    """

    text = str(value if value is not None else "").strip()
    if text in {"无", "--", "*", ""}:
        return {"status": "SOLD_OUT", "count": 0, "at_least": 0, "raw": text}
    if text == "有":
        return {
            "status": "AVAILABLE",
            "count": None,
            "at_least": EXACT_COUNT_CEILING + 1,
            "raw": text,
        }
    if text.isdigit():
        count = int(text)
        status = "SOLD_OUT" if count == 0 else "LIMITED"
        return {"status": status, "count": count, "at_least": count, "raw": text}
    return {"status": "UNKNOWN", "count": None, "at_least": 0, "raw": text}


def train_category(train_no: Any) -> str:
    """Map a train code such as ``G1321`` to its service class."""

    code = str(train_no or "").strip().upper()
    if not code:
        return "未知"
    return TRAIN_CATEGORIES.get(code[0], "普速")


def normalize_train(train: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a single train entry from ``query-tickets``."""

    if not isinstance(train, dict):
        raise RailDataError("每条车次必须是对象")

    seats = train.get("seats") or {}
    if not isinstance(seats, dict):
        raise RailDataError(f"{train.get('train_no')} 的 seats 字段格式无效")

    normalized_seats = {key: normalize_seat(value) for key, value in seats.items()}
    bookable = [
        key
        for key in SEAT_PREFERENCE
        if key in normalized_seats
        and normalized_seats[key]["status"] in {"AVAILABLE", "LIMITED"}
        and key != "no_seat"
    ]
    start_time = str(train.get("start_time") or "")
    arrive_time = str(train.get("arrive_time") or "")

    return {
        "train_no": str(train.get("train_no") or ""),
        "category": train_category(train.get("train_no")),
        "from_station": str(train.get("from_station") or ""),
        "from_station_code": str(train.get("from_station_code") or ""),
        "to_station": str(train.get("to_station") or ""),
        "to_station_code": str(train.get("to_station_code") or ""),
        "start_time": start_time,
        "arrive_time": arrive_time,
        "duration_minutes": parse_duration(train.get("duration")),
        # 12306 gives clock times only; a later arrival clock means next day.
        "arrives_next_day": bool(
            start_time and arrive_time and arrive_time < start_time
        ),
        "seats": normalized_seats,
        "bookable_classes": bookable,
        "has_seat_available": bool(bookable),
    }


def normalize_query_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a full ``query-tickets`` response."""

    if not isinstance(payload, dict):
        raise RailDataError("12306 返回必须是对象")
    trains = payload.get("trains")
    if not isinstance(trains, list):
        raise RailDataError("12306 返回缺少 trains 数组")

    normalized = [normalize_train(train) for train in trains]
    return {
        "success": bool(payload.get("success", True)),
        "from_station": str(payload.get("from_station") or ""),
        "to_station": str(payload.get("to_station") or ""),
        "train_date": str(payload.get("train_date") or ""),
        "count": len(normalized),
        "trains": normalized,
    }


def select_trains(
    trains: Iterable[Dict[str, Any]],
    *,
    seat_class: Optional[str] = None,
    earliest_departure: Optional[str] = None,
    latest_departure: Optional[str] = None,
    max_duration_minutes: Optional[int] = None,
    require_seat: bool = True,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Narrow a normalized train list down to usable candidates.

    Stations are deliberately not filtered here. A single city query returns
    every co-located station, and the fastest option is often not the one whose
    name matches the query, so the caller keeps that choice.
    """

    candidates = []
    for train in trains:
        if require_seat:
            if seat_class:
                seat = train.get("seats", {}).get(seat_class)
                if not seat or seat["status"] not in {"AVAILABLE", "LIMITED"}:
                    continue
            elif not train.get("has_seat_available"):
                continue
        departure = train.get("start_time") or ""
        if earliest_departure and departure < earliest_departure:
            continue
        if latest_departure and departure > latest_departure:
            continue
        duration = train.get("duration_minutes")
        if max_duration_minutes is not None and (
            duration is None or duration > max_duration_minutes
        ):
            continue
        candidates.append(train)

    candidates.sort(
        key=lambda item: (
            item.get("duration_minutes") if item.get("duration_minutes") is not None else 10**6,
            item.get("start_time") or "",
        )
    )
    return candidates[: max(0, limit)]


def train_to_activity(
    train: Dict[str, Any],
    depart_date: str,
    *,
    activity_id: Optional[str] = None,
    seat_class: Optional[str] = None,
    price_cny: Optional[float] = None,
    timezone_name: str = "Asia/Shanghai",
    utc_offset: str = "+08:00",
) -> Dict[str, Any]:
    """Convert a normalized train into an itinerary *activity*.

    A train ride is an activity, not a segment: its ``duration`` is how long
    the journey takes, whereas a segment measures the transfer between two
    activities. Getting to the station is a separate segment whose duration
    comes from a routing provider, not from 12306.

    ``price_cny`` must come from ``query-ticket-price``; ``query-tickets``
    carries no fare, so the fare is simply absent when the caller has not
    looked it up.
    """

    duration = train.get("duration_minutes")
    if duration is None:
        raise RailDataError(f"{train.get('train_no')} 缺少可用的历时字段")
    depart_time = train.get("start_time")
    arrive_time = train.get("arrive_time")
    if not depart_time or not arrive_time:
        raise RailDataError(f"{train.get('train_no')} 缺少发车或到达时间")

    try:
        start_day = date.fromisoformat(str(depart_date))
    except ValueError as exc:
        raise RailDataError(f"发车日期无效：{depart_date}") from exc
    end_day = start_day + timedelta(days=1) if train.get("arrives_next_day") else start_day

    chosen = seat_class
    if chosen is None:
        bookable = train.get("bookable_classes") or []
        chosen = bookable[0] if bookable else None

    train_no = train.get("train_no") or "train"
    activity: Dict[str, Any] = {
        "id": activity_id or f"train-{train_no}",
        "name": f"{train_no} {train.get('from_station')}→{train.get('to_station')}",
        "type": "TRAIN",
        "start": f"{start_day.isoformat()}T{depart_time}:00{utc_offset}",
        "end": f"{end_day.isoformat()}T{arrive_time}:00{utc_offset}",
        "timezone": timezone_name,
        # Boarding closes before departure, so the transfer into this activity
        # must clear the station gate, not merely reach the platform.
        "required_buffer_minutes": DEFAULT_RAIL_BUFFER_MINUTES,
        "duration_minutes": duration,
        "train_no": train_no,
        "category": train.get("category"),
        "from_station": train.get("from_station"),
        "to_station": train.get("to_station"),
        "arrives_next_day": train.get("arrives_next_day", False),
        "source": "12306",
    }
    if chosen:
        activity["seat_class"] = chosen
        activity["seat_class_label"] = SEAT_LABELS.get(chosen, chosen)
    if price_cny is not None:
        activity["estimated_cost"] = float(price_cny)
        activity["price_source"] = "12306:query-ticket-price"
    return activity


def summarize_availability(train: Dict[str, Any]) -> str:
    """Render a normalized train's seat availability for display."""

    parts = []
    for key in SEAT_PREFERENCE:
        seat = train.get("seats", {}).get(key)
        if not seat:
            continue
        label = SEAT_LABELS.get(key, key)
        if seat["status"] == "SOLD_OUT":
            parts.append(f"{label} 无")
        elif seat["status"] == "AVAILABLE":
            parts.append(f"{label} 充足")
        elif seat["status"] == "LIMITED":
            parts.append(f"{label} {seat['count']}")
        else:
            parts.append(f"{label} {seat['raw'] or '未知'}")
    return " | ".join(parts)
