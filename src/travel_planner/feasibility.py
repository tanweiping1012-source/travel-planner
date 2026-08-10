"""Deterministic feasibility checks for normalized itinerary JSON."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("datetime values must include a timezone offset")
    return parsed


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


def evaluate_itinerary(itinerary: Dict[str, Any], now: Optional[datetime] = None) -> dict:
    """Evaluate a normalized itinerary and return deterministic issues and a score."""

    now = now or datetime.now(timezone.utc)
    constraints = itinerary.get("constraints") or {}
    activities = list(itinerary.get("activities") or [])
    segments = list(itinerary.get("segments") or [])
    hard_conflicts: List[dict] = []
    warnings: List[dict] = []
    suggestions: List[str] = []

    parsed: List[Tuple[dict, datetime, datetime]] = []
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
        parsed.append((activity, start, end))

    parsed.sort(key=lambda item: item[1])
    by_id = {str(item[0].get("id")): item for item in parsed}
    segment_index = {
        (str(segment.get("from_id")), str(segment.get("to_id"))): segment
        for segment in segments
    }

    for index, current in enumerate(parsed[:-1]):
        current_activity, _, current_end = current
        next_activity, next_start, _ = parsed[index + 1]
        current_id = str(current_activity.get("id"))
        next_id = str(next_activity.get("id"))
        if next_start < current_end:
            overlap = int((current_end - next_start).total_seconds() / 60)
            hard_conflicts.append(
                _issue(
                    "ACTIVITY_OVERLAP",
                    "HARD",
                    f"{current_activity.get('name')} 与 {next_activity.get('name')} 重叠 {overlap} 分钟",
                    [current_id, next_id],
                    {"overlap_minutes": overlap},
                )
            )
            suggestions.append(f"调整 {next_activity.get('name')} 的开始时间或移动到其他日期")
            continue

        segment = segment_index.get((current_id, next_id))
        if not segment:
            warnings.append(
                _issue(
                    "MISSING_TRANSIT_SEGMENT",
                    "WARNING",
                    f"缺少 {current_activity.get('name')} 到 {next_activity.get('name')} 的真实通勤数据",
                    [current_id, next_id],
                )
            )
            continue

        travel_minutes = int(segment.get("duration_minutes") or 0)
        buffer_minutes = int(
            segment.get("buffer_minutes")
            or next_activity.get("required_buffer_minutes")
            or _default_departure_buffer(str(next_activity.get("type") or ""))
            or constraints.get("default_transfer_buffer_minutes")
            or 15
        )
        available_minutes = int((next_start - current_end).total_seconds() / 60)
        required_minutes = travel_minutes + buffer_minutes
        if available_minutes < required_minutes:
            shortage = required_minutes - available_minutes
            hard_conflicts.append(
                _issue(
                    "INSUFFICIENT_TRANSFER_TIME",
                    "HARD",
                    f"{current_activity.get('name')} 到 {next_activity.get('name')} 少预留 {shortage} 分钟",
                    [current_id, next_id],
                    {
                        "available_minutes": available_minutes,
                        "travel_minutes": travel_minutes,
                        "buffer_minutes": buffer_minutes,
                    },
                )
            )
            suggestions.append(f"将 {next_activity.get('name')} 至少延后 {shortage} 分钟")

    for activity, start, end in parsed:
        activity_id = str(activity.get("id"))
        local_start = start.timetz().replace(tzinfo=None)
        local_end = end.timetz().replace(tzinfo=None)
        opening = activity.get("opening_time")
        closing = activity.get("closing_time")
        last_entry = activity.get("last_entry_time")

        if opening and local_start < datetime.strptime(opening, "%H:%M").time():
            hard_conflicts.append(
                _issue(
                    "BEFORE_OPENING",
                    "HARD",
                    f"{activity.get('name')} 的到达时间早于开放时间 {opening}",
                    [activity_id],
                )
            )
        if closing and local_end > datetime.strptime(closing, "%H:%M").time():
            hard_conflicts.append(
                _issue(
                    "AFTER_CLOSING",
                    "HARD",
                    f"{activity.get('name')} 的结束时间晚于闭馆时间 {closing}",
                    [activity_id],
                )
            )
        if last_entry and local_start > datetime.strptime(last_entry, "%H:%M").time():
            hard_conflicts.append(
                _issue(
                    "AFTER_LAST_ENTRY",
                    "HARD",
                    f"到达 {activity.get('name')} 时已超过停止入场时间 {last_entry}",
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
    for item in parsed:
        daily[item[1].date().isoformat()].append(item)

    max_daily_minutes = int(constraints.get("max_daily_minutes") or 720)
    max_walking_km = float(constraints.get("max_walking_km_per_day") or 12)
    for day, day_items in daily.items():
        span_minutes = int((day_items[-1][2] - day_items[0][1]).total_seconds() / 60)
        walking_km = sum(float(item[0].get("walking_km") or 0) for item in day_items)
        if span_minutes > max_daily_minutes:
            warnings.append(
                _issue(
                    "DAILY_DURATION_EXCEEDED",
                    "WARNING",
                    f"{day} 行程跨度 {span_minutes} 分钟，超过上限 {max_daily_minutes} 分钟",
                    [str(item[0].get("id")) for item in day_items],
                )
            )
            suggestions.append(f"减少 {day} 的活动，或将低优先级景点移到其他日期")
        if walking_km > max_walking_km:
            warnings.append(
                _issue(
                    "WALKING_LIMIT_EXCEEDED",
                    "WARNING",
                    f"{day} 预计步行 {walking_km:.1f} 公里，超过上限 {max_walking_km:.1f} 公里",
                    [str(item[0].get("id")) for item in day_items],
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

    score = max(0, 100 - len(hard_conflicts) * 30 - len(warnings) * 8)
    return {
        "status": status,
        "score": score,
        "hard_conflicts": hard_conflicts,
        "warnings": warnings,
        "suggestions": list(dict.fromkeys(suggestions)),
        "summary": {
            "activity_count": len(activities),
            "segment_count": len(segments),
            "estimated_cost_cny": round(estimated_cost, 2),
        },
    }
