"""Validate browser-derived lodging offers.

Hotels behave unlike every other source here, in two ways that decide the
design.

**The price depends on who is looking.** An OTA shows a signed-out visitor no
price at all, and shows a signed-in one a price scaled to their membership
tier — the same room listed at 609 and sold at 479 to a diamond member. A
lodging figure is therefore meaningless without the login state and tier that
produced it, and two figures gathered under different states are not
comparable. Both are required rather than optional.

**The number on the card is per night, for the cheapest room.** `¥556 起` is
not what a six-night stay costs, and it is not what the room the traveller
actually wants costs. Confusing the two understates a week's accommodation by
a factor of six, so the basis is recorded explicitly and a total is only ever
derived by :func:`total_for_stay`, never read off the page.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from travel_planner.timeutil import parse_datetime as _parse_datetime
from travel_planner.timeutil import require_aware

#: Hotel prices move more slowly than airfares but availability in a holiday
#: peak does not, so a lookup is good for part of a day rather than hours.
DEFAULT_MAX_AGE_HOURS = 12

#: A price is per night unless the page says otherwise.
PRICE_BASES = ("PER_NIGHT", "TOTAL_STAY")

#: Login states that can produce a price at all.
PRICED_LOGIN_STATES = ("CONNECTED", "PUBLIC_READY")


class LodgingDataError(ValueError):
    """Raised when a lodging offer cannot be interpreted."""


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


def nights_between(check_in: Any, check_out: Any) -> int:
    """Nights covered by a stay, which is the date difference, not the days."""

    try:
        start = date.fromisoformat(str(check_in))
        end = date.fromisoformat(str(check_out))
    except ValueError as exc:
        raise LodgingDataError(f"入离日期无效：{check_in} → {check_out}") from exc
    nights = (end - start).days
    if nights <= 0:
        raise LodgingDataError(
            f"离店日期必须晚于入住日期：{check_in} → {check_out}"
        )
    return nights


def total_for_stay(offer: Dict[str, Any], rooms: int = 1) -> float:
    """Cost of the whole stay, derived rather than read off the page.

    A card price is per night for the cheapest room, so a six-night stay costs
    six times what the listing shows — the single easiest way to understate an
    accommodation budget.
    """

    price = offer.get("displayed_price")
    if price is None:
        raise LodgingDataError("住宿记录缺少可见价格")
    basis = str(offer.get("price_basis") or "PER_NIGHT").upper()
    if basis not in PRICE_BASES:
        raise LodgingDataError(f"未知的计价口径：{basis}")
    if rooms < 1:
        raise LodgingDataError("房间数必须至少为 1")

    if basis == "TOTAL_STAY":
        return float(price) * rooms
    nights = nights_between(offer.get("check_in"), offer.get("check_out"))
    return float(price) * nights * rooms


def normalize_offer(offer: Dict[str, Any], rooms: int = 1) -> Dict[str, Any]:
    """Normalize one lodging offer, deriving the stay total."""

    if not isinstance(offer, dict):
        raise LodgingDataError("住宿记录必须是对象")
    source = offer.get("source") or {}
    if not isinstance(source, dict):
        source = {}

    nights = nights_between(offer.get("check_in"), offer.get("check_out"))
    return {
        "offer_id": str(offer.get("offer_id") or ""),
        "name": str(offer.get("name") or ""),
        "city": str(offer.get("city") or ""),
        "room_type": str(offer.get("room_type") or ""),
        "check_in": str(offer.get("check_in") or ""),
        "check_out": str(offer.get("check_out") or ""),
        "nights": nights,
        "rooms": rooms,
        "displayed_price": offer.get("displayed_price"),
        "price_basis": str(offer.get("price_basis") or "PER_NIGHT").upper(),
        "total_cny": total_for_stay(offer, rooms),
        "free_cancellation": bool(offer.get("free_cancellation")),
        "rating": offer.get("rating"),
        "login_state": str(source.get("login_state") or ""),
        "member_tier": str(source.get("member_tier") or ""),
        "channel": str(source.get("channel") or ""),
        "checked_at": str(source.get("checked_at") or ""),
    }


def validate_offers(
    offers: List[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
    rooms: int = 1,
) -> dict:
    """Check browser-derived lodging offers.

    As with flights, structural checks always run and freshness is only
    evaluated when ``now`` is supplied.
    """

    if now is not None:
        require_aware(now)

    hard_conflicts: List[dict] = []
    warnings: List[dict] = []
    normalized: List[dict] = []
    tiers = set()

    for offer in offers or []:
        offer_id = str(offer.get("offer_id") or "") if isinstance(offer, dict) else ""
        try:
            record = normalize_offer(offer, rooms)
        except LodgingDataError as exc:
            hard_conflicts.append(
                _issue("INVALID_LODGING_OFFER", "HARD", str(exc), offer_id)
            )
            continue
        normalized.append(record)

        if not record["channel"] or not record["checked_at"]:
            hard_conflicts.append(
                _issue(
                    "MISSING_SOURCE_METADATA",
                    "HARD",
                    "住宿记录缺少渠道或查询时间",
                    offer_id,
                )
            )
        if not record["login_state"]:
            hard_conflicts.append(
                _issue(
                    "MISSING_LOGIN_STATE",
                    "HARD",
                    "住宿价格随登录态变化，未记录登录态的价格无法与其他报价比较",
                    offer_id,
                )
            )
        elif record["login_state"] not in PRICED_LOGIN_STATES:
            hard_conflicts.append(
                _issue(
                    "UNPRICED_LOGIN_STATE",
                    "HARD",
                    f"登录态为 {record['login_state']}，该状态下 OTA 不展示房价",
                    offer_id,
                )
            )
        elif record["login_state"] == "CONNECTED" and not record["member_tier"]:
            warnings.append(
                _issue(
                    "MEMBER_TIER_UNRECORDED",
                    "WARNING",
                    "已登录但未记录会员等级；会员价与他人看到的价格可能不同",
                    offer_id,
                )
            )
        if record["login_state"] in PRICED_LOGIN_STATES:
            # Comparability is decided by the whole viewing context, not the
            # tier alone: a public price and a member price differ even though
            # neither carries a tier the other could be compared against.
            tiers.add(
                f"{record['login_state']}/{record['member_tier'] or '无等级'}"
            )

        if record["checked_at"] and now is not None:
            try:
                age = (now - _parse_datetime(record["checked_at"])).total_seconds() / 3600
            except ValueError:
                hard_conflicts.append(
                    _issue(
                        "INVALID_SOURCE_TIME", "HARD", "住宿记录的查询时间无效", offer_id
                    )
                )
            else:
                if age > max_age_hours:
                    warnings.append(
                        _issue(
                            "STALE_LODGING_PRICE",
                            "WARNING",
                            f"房价已查询 {age:.1f} 小时，超过 {max_age_hours} 小时上限",
                            offer_id,
                            {"age_hours": round(age, 1)},
                        )
                    )

        if not record["free_cancellation"]:
            warnings.append(
                _issue(
                    "NO_FREE_CANCELLATION",
                    "WARNING",
                    "该房型不可免费取消，行程调整时无法退改",
                    offer_id,
                )
            )

    if len(tiers) > 1:
        warnings.append(
            _issue(
                "MIXED_VIEWING_CONTEXTS",
                "WARNING",
                "报价来自不同的登录态或会员等级（"
                + "、".join(sorted(tiers))
                + "），彼此不可直接比较；请在同一登录态下重查后再排序",
                details={"contexts": sorted(tiers)},
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
        "offers": normalized,
        "summary": {
            "offer_count": len(offers or []),
            "rooms": rooms,
            "total_cny": round(sum(item["total_cny"] for item in normalized), 2),
            "freshness_checked": now is not None,
        },
    }
