"""Deterministic feasibility checks for normalized itinerary JSON."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, NamedTuple, Optional

try:  # pragma: no cover - depends on the platform tz database
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


_TIME_WINDOW_FIELDS = ("opening_time", "closing_time", "last_entry_time")


class _Entry(NamedTuple):
    """An activity paired with both its absolute and its venue-local times."""

    activity: dict
    start: datetime
    end: datetime
    local_start: datetime
    local_end: datetime
    zone_declared: bool


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("datetime values must include a timezone offset")
    return parsed


def _parse_clock(value: Any) -> Optional[time]:
    """Parse a ``HH:MM`` string, returning None when it is malformed."""

    try:
        return datetime.strptime(str(value), "%H:%M").time()
    except (TypeError, ValueError):
        return None


def _resolve_zone(name: Any):
    """Resolve an IANA timezone name, returning None when unusable."""

    if not name or ZoneInfo is None:
        return None
    try:
        return ZoneInfo(str(name))
    except Exception:  # noqa: BLE001 - unknown zone or missing tz database
        return None


def _to_local(moment: datetime, zone) -> datetime:
    """Wall-clock time at the venue.

    With a declared zone the instant is converted properly. Without one we fall
    back to reading the offset carried by the timestamp as if it were local,
    which is only correct when the producer wrote destination-local times.
    """

    if zone is not None:
        return moment.astimezone(zone).replace(tzinfo=None)
    return moment.replace(tzinfo=None)


def _issue(
    code: str,
    severity: str,
    message: str,
    activity_ids: Optional[List[str]] = None,
    details: Optional[dict] = None,
) -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "activity_ids": activity_ids or [],
        "details": details or {},
    }


def _default_departure_buffer(activity_type: str) -> int:
    return {
        "FLIGHT_DOMESTIC": 120,
        "FLIGHT_INTERNATIONAL": 180,
        "TRAIN": 45,
        "BUS": 30,
    }.get(activity_type.upper(), 0)


def _first_present(*values: Any) -> Optional[int]:
    """First value that is actually supplied, so an explicit 0 is honoured."""

    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _score(hard_conflicts: List[dict], warnings: List[dict]) -> int:
    """Score within status bands so a blocked plan never outranks a risky one."""

    if hard_conflicts:
        return max(0, 40 - len(hard_conflicts) * 8 - len(warnings) * 2)
    if warnings:
        return max(60, 95 - len(warnings) * 7)
    return 100


def evaluate_itinerary(itinerary: Dict[str, Any], now: Optional[datetime] = None) -> dict:
    """Evaluate a normalized itinerary and return deterministic issues and a score."""

    now = now or datetime.now(timezone.utc)
    constraints = itinerary.get("constraints") or {}
    activities = list(itinerary.get("activities") or [])
    segments = list(itinerary.get("segments") or [])
    hard_conflicts: List[dict] = []
    warnings: List[dict] = []
    suggestions: List[str] = []

    trip_zone_name = itinerary.get("timezone")
    trip_zone = _resolve_zone(trip_zone_name)
    if trip_zone_name and trip_zone is None:
        warnings.append(
            _issue(
                "UNKNOWN_TIMEZONE",
                "WARNING",
                f"无法识别时区 {trip_zone_name}，已回退到时间戳自带的偏移量",
                details={"timezone": str(trip_zone_name)},
            )
        )

    parsed: List[_Entry] = []
    for activity in activities:
        activity_id = str(activity.get("id") or "")
        try:
            start = _parse_datetime(str(activity["start"]))
            end = _parse_datetime(str(activity["end"]))
        except (KeyError, TypeError, ValueError) as exc:
            hard_conflicts.append(
                _issue(
                    "INVALID_ACTIVITY_TIME",
                    "HARD",
                    f"活动 {activity_id or 'unknown'} 的时间格式无效：{exc}",
                    [activity_id] if activity_id else [],
                )
            )
            continue
        if end <= start:
            hard_conflicts.append(
                _issue(
                    "INVALID_ACTIVITY_RANGE",
                    "HARD",
                    f"活动 {activity.get('name') or activity_id} 的结束时间不晚于开始时间",
                    [activity_id],
                )
            )
            continue

        own_zone_name = activity.get("timezone")
        own_zone = _resolve_zone(own_zone_name)
        if own_zone_name and own_zone is None:
            warnings.append(
                _issue(
                    "UNKNOWN_TIMEZONE",
                    "WARNING",
                    f"{activity.get('name') or activity_id} 的时区 {own_zone_name} 无法识别",
                    [activity_id],
                    {"timezone": str(own_zone_name)},
                )
            )
        zone = own_zone or trip_zone
        parsed.append(
            _Entry(
                activity=activity,
                start=start,
                end=end,
                local_start=_to_local(start, zone),
                local_end=_to_local(end, zone),
                zone_declared=zone is not None,
            )
        )

    parsed.sort(key=lambda entry: entry.start)
    segment_index = {
        (str(segment.get("from_id")), str(segment.get("to_id"))): segment
        for segment in segments
    }

    for index, current in enumerate(parsed[:-1]):
        following = parsed[index + 1]
        current_id = str(current.activity.get("id"))
        next_id = str(following.activity.get("id"))
        if following.start < current.end:
            overlap = int((current.end - following.start).total_seconds() / 60)
            hard_conflicts.append(
                _issue(
                    "ACTIVITY_OVERLAP",
                    "HARD",
                    f"{current.activity.get('name')} 与 {following.activity.get('name')} 重叠 {overlap} 分钟",
                    [current_id, next_id],
                    {"overlap_minutes": overlap},
                )
            )
            suggestions.append(
                f"调整 {following.activity.get('name')} 的开始时间或移动到其他日期"
            )
            continue

        segment = segment_index.get((current_id, next_id))
        same_day = current.local_end.date() == following.local_start.date()
        if not segment:
            # Across an overnight break there is no transfer to model, so a
            # missing segment is expected rather than a gap in the research.
            if same_day:
                warnings.append(
                    _issue(
                        "MISSING_TRANSIT_SEGMENT",
                        "WARNING",
                        f"缺少 {current.activity.get('name')} 到 {following.activity.get('name')} 的真实通勤数据",
                        [current_id, next_id],
                    )
                )
            continue

        travel_minutes = int(segment.get("duration_minutes") or 0)
        buffer_minutes = _first_present(
            segment.get("buffer_minutes"),
            following.activity.get("required_buffer_minutes"),
            _default_departure_buffer(str(following.activity.get("type") or "")) or None,
            constraints.get("default_transfer_buffer_minutes"),
        )
        if buffer_minutes is None:
            buffer_minutes = 15
        available_minutes = int((following.start - current.end).total_seconds() / 60)
        required_minutes = travel_minutes + buffer_minutes
        if available_minutes < required_minutes:
            shortage = required_minutes - available_minutes
            hard_conflicts.append(
                _issue(
                    "INSUFFICIENT_TRANSFER_TIME",
                    "HARD",
                    f"{current.activity.get('name')} 到 {following.activity.get('name')} 少预留 {shortage} 分钟",
                    [current_id, next_id],
                    {
                        "available_minutes": available_minutes,
                        "travel_minutes": travel_minutes,
                        "buffer_minutes": buffer_minutes,
                    },
                )
            )
            suggestions.append(
                f"将 {following.activity.get('name')} 至少延后 {shortage} 分钟"
            )

    for entry in parsed:
        activity = entry.activity
        activity_id = str(activity.get("id"))
        local_start = entry.local_start.time()
        local_end = entry.local_end.time()

        declared_windows = [
            field for field in _TIME_WINDOW_FIELDS if activity.get(field)
        ]
        ambiguous_zone = (
            bool(declared_windows)
            and not entry.zone_declared
            and entry.start.utcoffset() == timedelta(0)
        )
        if ambiguous_zone:
            # The offset says UTC, which is almost never the venue's own clock.
            # Skip the window checks rather than block the plan on a comparison
            # we already know may be meaningless.
            warnings.append(
                _issue(
                    "AMBIGUOUS_TIMEZONE",
                    "WARNING",
                    f"{activity.get('name') or activity_id} 使用 UTC 时间但未声明时区，"
                    "已跳过营业时间检查，请补充 timezone 字段",
                    [activity_id],
                    {"skipped_checks": declared_windows},
                )
            )

        for field in declared_windows:
            if _parse_clock(activity.get(field)) is None:
                warnings.append(
                    _issue(
                        "INVALID_TIME_FORMAT",
                        "WARNING",
                        f"{activity.get('name') or activity_id} 的 {field} 格式无效，已跳过该项检查",
                        [activity_id],
                        {"field": field, "value": str(activity.get(field))},
                    )
                )

        if ambiguous_zone:
            opening = closing = last_entry = None
        else:
            opening = _parse_clock(activity.get("opening_time"))
            closing = _parse_clock(activity.get("closing_time"))
            last_entry = _parse_clock(activity.get("last_entry_time"))
        crosses_midnight = entry.local_end.date() != entry.local_start.date()

        if opening and local_start < opening:
            hard_conflicts.append(
                _issue(
                    "BEFORE_OPENING",
                    "HARD",
                    f"{activity.get('name')} 的到达时间早于开放时间 "
                    f"{activity.get('opening_time')}",
                    [activity_id],
                )
            )
        if closing and (crosses_midnight or local_end > closing):
            hard_conflicts.append(
                _issue(
                    "AFTER_CLOSING",
                    "HARD",
                    f"{activity.get('name')} 的结束时间晚于闭馆时间 "
                    f"{activity.get('closing_time')}",
                    [activity_id],
                )
            )
        if last_entry and local_start > last_entry:
            hard_conflicts.append(
                _issue(
                    "AFTER_LAST_ENTRY",
                    "HARD",
                    f"到达 {activity.get('name')} 时已超过停止入场时间 "
                    f"{activity.get('last_entry_time')}",
                    [activity_id],
                )
            )

        checked_at = activity.get("source_checked_at")
        if checked_at:
            stale_after_hours = int(constraints.get("stale_after_hours") or 24)
            try:
                age_hours = (now - _parse_datetime(str(checked_at))).total_seconds() / 3600
                if age_hours > stale_after_hours:
                    warnings.append(
                        _issue(
                            "STALE_SOURCE",
                            "WARNING",
                            f"{activity.get('name')} 的动态信息已超过 {stale_after_hours} 小时",
                            [activity_id],
                            {"age_hours": round(age_hours, 1)},
                        )
                    )
            except ValueError:
                warnings.append(
                    _issue(
                        "INVALID_SOURCE_TIME",
                        "WARNING",
                        f"{activity.get('name')} 的来源更新时间无效",
                        [activity_id],
                    )
                )

    daily = defaultdict(list)
    for entry in parsed:
        daily[entry.local_start.date().isoformat()].append(entry)

    max_daily_minutes = int(constraints.get("max_daily_minutes") or 720)
    max_walking_km = float(constraints.get("max_walking_km_per_day") or 12)
    for day, day_items in daily.items():
        span_minutes = int(
            (day_items[-1].end - day_items[0].start).total_seconds() / 60
        )
        walking_km = sum(
            float(entry.activity.get("walking_km") or 0) for entry in day_items
        )
        if span_minutes > max_daily_minutes:
            warnings.append(
                _issue(
                    "DAILY_DURATION_EXCEEDED",
                    "WARNING",
                    f"{day} 行程跨度 {span_minutes} 分钟，超过上限 {max_daily_minutes} 分钟",
                    [str(entry.activity.get("id")) for entry in day_items],
                )
            )
            suggestions.append(f"减少 {day} 的活动，或将低优先级景点移到其他日期")
        if walking_km > max_walking_km:
            warnings.append(
                _issue(
                    "WALKING_LIMIT_EXCEEDED",
                    "WARNING",
                    f"{day} 预计步行 {walking_km:.1f} 公里，超过上限 {max_walking_km:.1f} 公里",
                    [str(entry.activity.get("id")) for entry in day_items],
                )
            )

    estimated_cost = sum(float(item.get("estimated_cost") or 0) for item in activities)
    estimated_cost += sum(float(item.get("estimated_cost") or 0) for item in segments)
    budget = float(itinerary.get("budget_cny") or 0)
    if budget and estimated_cost > budget:
        warnings.append(
            _issue(
                "BUDGET_EXCEEDED",
                "WARNING",
                f"参考费用 ¥{estimated_cost:.2f} 超过预算 ¥{budget:.2f}",
                details={"estimated_cost": estimated_cost, "budget": budget},
            )
        )
        suggestions.append("优先替换费用较高的交通或非必去活动")

    if hard_conflicts:
        status = "INFEASIBLE"
    elif warnings:
        status = "FEASIBLE_WITH_RISK"
    else:
        status = "FEASIBLE"

    return {
        "status": status,
        "score": _score(hard_conflicts, warnings),
        "hard_conflicts": hard_conflicts,
        "warnings": warnings,
        "suggestions": list(dict.fromkeys(suggestions)),
        "summary": {
            "activity_count": len(activities),
            "segment_count": len(segments),
            "estimated_cost_cny": round(estimated_cost, 2),
        },
    }
