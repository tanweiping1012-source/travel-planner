"""Validate browser-derived flight offers and map them into itineraries.

Flights are the only data source in this Skill with no usable API, so an offer
is whatever an OTA page showed at one moment. Two consequences follow, and this
module exists for both.

A page price is not a payable price: ``final_price_guaranteed`` is almost never
true, and a plan must say so rather than presenting the number as settled.

A page price also goes stale quickly. Rail fares barely move, so a lookup from
yesterday is still informative; an airfare from three hours ago may not be.
Freshness is therefore checked only when the caller supplies ``now``, because
a stored plan is not necessarily a plan being presented — and the workflow
refreshes selected offers immediately before presentation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from travel_planner.timeutil import parse_datetime as _parse_datetime
from travel_planner.timeutil import require_aware

#: Airfares move on their own; anything older than this needs a refresh.
DEFAULT_MAX_AGE_HOURS = 2

#: Slack allowed between a stated duration and the one implied by the clock.
DURATION_TOLERANCE_MINUTES = 5

#: Gate-closing buffers, matching the FLIGHT defaults in
#: :mod:`travel_planner.feasibility`.
DOMESTIC_BUFFER_MINUTES = 120
INTERNATIONAL_BUFFER_MINUTES = 180

LEG_LABELS = {"outbound": "去程", "return": "返程"}


class FlightDataError(ValueError):
    """Raised when a flight offer cannot be interpreted at all."""


def _issue(
    code: str,
    severity: str,
    message: str,
    offer_id: str = "",
    details: Optional[dict] = None,
) -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "offer_id": offer_id,
        "details": details or {},
    }


def normalize_leg(leg: Dict[str, Any], label: str) -> Dict[str, Any]:
    """Normalize one leg, keeping both the stated and the implied duration."""

    if not isinstance(leg, dict):
        raise FlightDataError(f"{label} 必须是对象")

    departure = _parse_datetime(leg["departure"])
    arrival = _parse_datetime(leg["arrival"])
    implied = int((arrival - departure).total_seconds() / 60)
    stated = leg.get("duration_minutes")

    return {
        "leg": label,
        "carrier": str(leg.get("carrier") or ""),
        "flight_number": str(leg.get("flight_number") or ""),
        "origin_airport": str(leg.get("origin_airport") or ""),
        "destination_airport": str(leg.get("destination_airport") or ""),
        "departure": departure,
        "arrival": arrival,
        "stated_duration_minutes": int(stated) if stated is not None else None,
        "implied_duration_minutes": implied,
        "stops": int(leg.get("stops") or 0),
    }


def validate_offers(
    offers: List[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
) -> dict:
    """Check browser-derived flight offers.

    Structural checks always run. Freshness is evaluated only when ``now`` is
    supplied, so validating a stored plan does not fail merely because time
    has passed since it was written.
    """

    if now is not None:
        require_aware(now)

    hard_conflicts: List[dict] = []
    warnings: List[dict] = []
    checked = 0

    for offer in offers or []:
        if not isinstance(offer, dict):
            hard_conflicts.append(
                _issue("INVALID_OFFER", "HARD", "机票记录必须是对象")
            )
            continue
        offer_id = str(offer.get("offer_id") or "")
        source = offer.get("source") or {}
        if not isinstance(source, dict):
            source = {}

        channel = source.get("channel")
        checked_at_raw = source.get("checked_at")
        if not channel or not checked_at_raw:
            hard_conflicts.append(
                _issue(
                    "MISSING_SOURCE_METADATA",
                    "HARD",
                    "浏览器获取的机票记录缺少渠道或查询时间",
                    offer_id,
                )
            )
        elif now is not None:
            try:
                age_hours = (now - _parse_datetime(checked_at_raw)).total_seconds() / 3600
            except ValueError:
                hard_conflicts.append(
                    _issue(
                        "INVALID_SOURCE_TIME",
                        "HARD",
                        "机票记录的查询时间格式无效",
                        offer_id,
                    )
                )
            else:
                if age_hours > max_age_hours:
                    warnings.append(
                        _issue(
                            "STALE_FLIGHT_PRICE",
                            "WARNING",
                            f"机票价格已查询 {age_hours:.1f} 小时，"
                            f"超过 {max_age_hours} 小时上限，呈现前需要重新查询",
                            offer_id,
                            {"age_hours": round(age_hours, 1)},
                        )
                    )

        for label in ("outbound", "return"):
            leg = offer.get(label)
            if leg is None:
                continue
            try:
                normalized = normalize_leg(leg, label)
            except (FlightDataError, KeyError, TypeError, ValueError) as exc:
                hard_conflicts.append(
                    _issue(
                        "INVALID_FLIGHT_LEG",
                        "HARD",
                        f"{LEG_LABELS[label]}航段无法解析：{exc}",
                        offer_id,
                    )
                )
                continue
            checked += 1

            if normalized["implied_duration_minutes"] <= 0:
                hard_conflicts.append(
                    _issue(
                        "ARRIVAL_BEFORE_DEPARTURE",
                        "HARD",
                        f"{LEG_LABELS[label]} {normalized['flight_number']} 的"
                        "落地时间不晚于起飞时间",
                        offer_id,
                    )
                )
                continue

            stated = normalized["stated_duration_minutes"]
            implied = normalized["implied_duration_minutes"]
            if stated is not None and abs(stated - implied) > DURATION_TOLERANCE_MINUTES:
                warnings.append(
                    _issue(
                        "DURATION_MISMATCH",
                        "WARNING",
                        f"{LEG_LABELS[label]} {normalized['flight_number']} 标注时长 "
                        f"{stated} 分钟，与起降时间推算的 {implied} 分钟不符",
                        offer_id,
                        {"stated": stated, "implied": implied},
                    )
                )

        if not offer.get("final_price_guaranteed"):
            warnings.append(
                _issue(
                    "PRICE_NOT_GUARANTEED",
                    "WARNING",
                    "网页可见价不是最终支付价，方案中必须标注该限制",
                    offer_id,
                )
            )
        raw_price = offer.get("displayed_total_price")
        if raw_price is None:
            warnings.append(
                _issue("MISSING_PRICE", "WARNING", "机票记录缺少可见价格", offer_id)
            )
        else:
            # An OTA card reads "¥3,583"; a price lifted verbatim would only
            # fail much later, inside offer_to_activity, with float()'s own
            # unhelpful message. A negative fare corrupts a budget silently.
            try:
                price_value = float(raw_price)
            except (TypeError, ValueError):
                hard_conflicts.append(
                    _issue(
                        "INVALID_PRICE",
                        "HARD",
                        f"价格无法解析为数字：{raw_price!r}；"
                        "请去掉货币符号与千分位后再记录",
                        offer_id,
                    )
                )
            else:
                if price_value < 0:
                    hard_conflicts.append(
                        _issue(
                            "INVALID_PRICE",
                            "HARD",
                            f"价格不能为负：{price_value}",
                            offer_id,
                        )
                    )
        if str(offer.get("baggage_visibility") or "UNKNOWN").upper() == "UNKNOWN":
            warnings.append(
                _issue(
                    "BAGGAGE_UNKNOWN",
                    "WARNING",
                    "页面未显示行李额度，比价时需自行确认",
                    offer_id,
                )
            )

    if hard_conflicts:
        status = "INVALID"
    elif warnings:
        status = "VALID_WITH_RISK"
    else:
        status = "VALID"

    return {
        "status": status,
        "hard_conflicts": hard_conflicts,
        "warnings": warnings,
        "summary": {
            "offer_count": len(offers or []),
            "leg_count": checked,
            "freshness_checked": now is not None,
            "max_age_hours": max_age_hours,
        },
    }


def offer_to_activity(
    offer: Dict[str, Any],
    *,
    leg: str = "outbound",
    activity_id: Optional[str] = None,
    international: bool = False,
    timezone_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert one leg of an offer into an itinerary activity.

    Like a train, a flight is an activity rather than a segment: the flight
    time is the ride, and reaching the airport is a separate segment whose
    duration comes from a routing provider.
    """

    raw_leg = offer.get(leg)
    if raw_leg is None:
        raise FlightDataError(f"机票记录缺少 {leg} 航段")
    try:
        normalized = normalize_leg(raw_leg, leg)
    except (KeyError, TypeError, ValueError) as exc:
        # A missing departure or arrival must surface as this module's own
        # error; a bare KeyError is not a ValueError and would escape the
        # CLI's handler as an unhandled traceback.
        raise FlightDataError(f"{LEG_LABELS.get(leg, leg)}航段无法解析：{exc}") from exc

    flight_number = normalized["flight_number"] or "flight"
    activity: Dict[str, Any] = {
        "id": activity_id or f"flight-{flight_number}",
        "name": f"{flight_number} {normalized['origin_airport']}→"
        f"{normalized['destination_airport']}",
        "type": "FLIGHT_INTERNATIONAL" if international else "FLIGHT_DOMESTIC",
        "start": normalized["departure"].isoformat(),
        "end": normalized["arrival"].isoformat(),
        "required_buffer_minutes": (
            INTERNATIONAL_BUFFER_MINUTES if international else DOMESTIC_BUFFER_MINUTES
        ),
        "duration_minutes": normalized["implied_duration_minutes"],
        "carrier": normalized["carrier"],
        "flight_number": flight_number,
        "origin_airport": normalized["origin_airport"],
        "destination_airport": normalized["destination_airport"],
        "stops": normalized["stops"],
        "source": (offer.get("source") or {}).get("channel") or "ota-browser",
        "price_is_final": bool(offer.get("final_price_guaranteed")),
    }
    if timezone_name:
        activity["timezone"] = timezone_name
    price = offer.get("displayed_total_price")
    if price is not None:
        try:
            activity["estimated_cost"] = float(price)
        except (TypeError, ValueError) as exc:
            raise FlightDataError(
                f"价格无法解析为数字：{price!r}；请去掉货币符号与千分位后再记录"
            ) from exc
        activity["price_source"] = activity["source"]
        checked_at = (offer.get("source") or {}).get("checked_at")
        if checked_at:
            activity["source_checked_at"] = str(checked_at)
    return activity
