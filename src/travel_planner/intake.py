"""Deterministic validation for travel-planning intake requests."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List


REQUIRED_FIELDS = (
    "origin",
    "destination",
    "start_date",
    "end_date",
    "travelers",
    "budget_cny",
    "budget_scope",
    "style",
    "must_visit",
    "excluded_places",
    "mobility",
    "tradeoff_priority",
    "risk_tolerance",
    "browser_approval",
)

VALID_BUDGET_SCOPES = {"PER_PERSON", "PARTY_TOTAL"}
VALID_PLACE_PRIORITIES = {"CORE", "IMPORTANT", "OPTIONAL"}
VALID_MOBILITY_LEVELS = {"LOW", "MODERATE", "HIGH"}
VALID_TRADEOFFS = {"CORE_PLACES", "COST", "PACE", "COMFORT"}
VALID_BROWSER_APPROVALS = {
    "ANONYMOUS_ONLY",
    "ALLOW_MANUAL_LOGIN",
    "DENY",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_date(value: Any) -> date:
    return date.fromisoformat(_text(value))


def _add_unique(items: List[str], value: str) -> None:
    if value not in items:
        items.append(value)


def validate_trip_request(request: Dict[str, Any]) -> dict:
    """Return whether a request can proceed without asking follow-up questions."""

    if not isinstance(request, dict):
        return {
            "status": "INVALID",
            "missing_fields": [],
            "errors": ["Trip request must be a JSON object"],
            "conflicts": [],
            "assumptions": [],
            "questions_required": [],
        }

    missing = [
        field
        for field in REQUIRED_FIELDS
        if field not in request or request[field] is None
    ]
    errors: List[str] = []
    conflicts: List[str] = []
    assumptions: List[str] = []
    questions: List[str] = []

    for field in ("origin", "destination", "style"):
        if field in request and not _text(request.get(field)):
            _add_unique(errors, f"{field} must not be empty")

    if "travelers" in request:
        travelers = request.get("travelers")
        if not isinstance(travelers, int) or isinstance(travelers, bool) or travelers < 1:
            errors.append("travelers must be a positive integer")

    if "budget_cny" in request:
        budget = request.get("budget_cny")
        if (
            not isinstance(budget, (int, float))
            or isinstance(budget, bool)
            or budget <= 0
        ):
            errors.append("budget_cny must be a positive number")

    budget_scope = _text(request.get("budget_scope")).upper()
    if "budget_scope" in request and budget_scope not in VALID_BUDGET_SCOPES:
        errors.append(
            "budget_scope must be PER_PERSON or PARTY_TOTAL"
        )

    if "start_date" in request and "end_date" in request:
        try:
            start_date = _parse_date(request.get("start_date"))
            end_date = _parse_date(request.get("end_date"))
            if end_date < start_date:
                errors.append("end_date must not be earlier than start_date")
        except ValueError:
            errors.append("start_date and end_date must use YYYY-MM-DD")

    must_visit = request.get("must_visit")
    must_visit_names = set()
    if "must_visit" in request:
        if not isinstance(must_visit, list):
            errors.append("must_visit must be an array")
        else:
            for index, place in enumerate(must_visit):
                if not isinstance(place, dict):
                    errors.append(f"must_visit[{index}] must be an object")
                    continue
                name = _text(place.get("name"))
                priority = _text(place.get("priority")).upper()
                if not name:
                    errors.append(f"must_visit[{index}].name must not be empty")
                else:
                    must_visit_names.add(name.casefold())
                if priority not in VALID_PLACE_PRIORITIES:
                    errors.append(
                        f"must_visit[{index}].priority must be CORE, "
                        "IMPORTANT, or OPTIONAL"
                    )

    excluded_places = request.get("excluded_places")
    excluded_names = set()
    if "excluded_places" in request:
        if not isinstance(excluded_places, list):
            errors.append("excluded_places must be an array")
        else:
            excluded_names = {
                _text(place).casefold()
                for place in excluded_places
                if _text(place)
            }

    overlap = sorted(must_visit_names & excluded_names)
    if overlap:
        conflicts.append(
            "Places cannot be both required and excluded: " + ", ".join(overlap)
        )

    mobility = request.get("mobility")
    if "mobility" in request:
        if not isinstance(mobility, dict):
            errors.append("mobility must be an object")
        else:
            level = _text(mobility.get("level")).upper()
            if level not in VALID_MOBILITY_LEVELS:
                errors.append("mobility.level must be LOW, MODERATE, or HIGH")
            walking = mobility.get("max_walking_km_per_day")
            if (
                not isinstance(walking, (int, float))
                or isinstance(walking, bool)
                or walking < 0
            ):
                errors.append(
                    "mobility.max_walking_km_per_day must be a non-negative number"
                )
            if not isinstance(mobility.get("accepts_high_altitude"), bool):
                errors.append("mobility.accepts_high_altitude must be boolean")
            if "accessibility_needs" not in mobility:
                assumptions.append("No accessibility needs were provided")
            elif not isinstance(mobility.get("accessibility_needs"), list):
                errors.append("mobility.accessibility_needs must be an array")

    priorities = request.get("tradeoff_priority")
    if "tradeoff_priority" in request:
        if not isinstance(priorities, list) or not priorities:
            errors.append("tradeoff_priority must be a non-empty array")
        else:
            normalized_priorities = [_text(item).upper() for item in priorities]
            invalid = [
                item for item in normalized_priorities if item not in VALID_TRADEOFFS
            ]
            if invalid:
                errors.append(
                    "tradeoff_priority contains invalid values: "
                    + ", ".join(invalid)
                )
            if len(set(normalized_priorities)) != len(normalized_priorities):
                errors.append("tradeoff_priority must not contain duplicates")

    risk = request.get("risk_tolerance")
    if "risk_tolerance" in request:
        if not isinstance(risk, dict):
            errors.append("risk_tolerance must be an object")
        elif not isinstance(risk.get("accepts_weather_dependent_core"), bool):
            errors.append(
                "risk_tolerance.accepts_weather_dependent_core must be boolean"
            )

    browser_approval = request.get("browser_approval")
    if "browser_approval" in request:
        if not isinstance(browser_approval, dict):
            errors.append("browser_approval must be an object")
        else:
            for provider in ("xiaohongshu", "ota"):
                value = _text(browser_approval.get(provider)).upper()
                if value not in VALID_BROWSER_APPROVALS:
                    errors.append(
                        f"browser_approval.{provider} must be ANONYMOUS_ONLY, "
                        "ALLOW_MANUAL_LOGIN, or DENY"
                    )

    if missing:
        questions.append(
            "Provide the missing intake fields in one response: "
            + ", ".join(missing)
        )
    if conflicts:
        questions.extend(conflicts)

    if errors:
        status = "INVALID"
    elif missing or conflicts:
        status = "NEEDS_CLARIFICATION"
    else:
        status = "READY"

    return {
        "status": status,
        "missing_fields": missing,
        "errors": errors,
        "conflicts": conflicts,
        "assumptions": assumptions,
        "questions_required": questions,
    }
