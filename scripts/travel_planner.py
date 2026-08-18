#!/usr/bin/env python3
"""CLI entry point for the travel planner MVP skill."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "src"))

from travel_planner.amap import AmapClient, AmapError  # noqa: E402
from travel_planner.credentials import (  # noqa: E402
    CredentialError,
    KeychainCredentialStore,
)
from travel_planner.diagnostics import build_doctor_report  # noqa: E402
from travel_planner.feasibility import evaluate_itinerary  # noqa: E402
from travel_planner.flight import validate_offers  # noqa: E402
from travel_planner.flight import (  # noqa: E402
    DEFAULT_MAX_AGE_HOURS,
    validate_offers,
)
from travel_planner.intake import validate_trip_request  # noqa: E402
from travel_planner.lodging import validate_offers as validate_lodging  # noqa: E402
from travel_planner.models import to_dict  # noqa: E402
from travel_planner.rail import (  # noqa: E402
    normalize_query_result,
    select_trains,
)
from travel_planner.research import (  # noqa: E402
    compile_destination_brief,
    validate_plan_content,
)
from travel_planner.workflow import collect_amap_snapshot  # noqa: E402


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--now must include a timezone offset")
    return parsed


def _read_json(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _emit(data: dict, output: str = None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        Path(output).write_text(f"{text}\n", encoding="utf-8")
    else:
        print(text)


def _amap_client() -> AmapClient:
    key = KeychainCredentialStore().get("amap")
    return AmapClient(key)


def command_credential_status(args: argparse.Namespace) -> None:
    _emit(KeychainCredentialStore().status("amap"))


def command_preflight(args: argparse.Namespace) -> None:
    _emit(_amap_client().preflight())


def command_doctor(args: argparse.Namespace) -> None:
    credential_store = KeychainCredentialStore()
    amap_status = credential_store.status("amap")
    if args.live and amap_status["status"] == "CONFIGURED":
        try:
            amap_status = _amap_client().preflight()
        except (CredentialError, AmapError, OSError) as exc:
            amap_status = {
                "provider": "amap",
                "status": "ERROR",
                "error_type": exc.__class__.__name__,
                "message": str(exc),
            }
    _emit(
        build_doctor_report(
            amap_status,
            browser_status=args.browser_status,
            client=args.client,
        )
    )


def command_validate_request(args: argparse.Namespace) -> None:
    report = validate_trip_request(_read_json(args.input))
    _emit(report, args.output)
    if report["status"] == "INVALID":
        raise SystemExit(2)


def command_search_places(args: argparse.Namespace) -> None:
    places = _amap_client().search_places(args.keywords, args.city, args.limit)
    _emit({"places": [to_dict(place) for place in places]})


def command_amap_snapshot(args: argparse.Namespace) -> None:
    request = _read_json(args.input)
    _emit(collect_amap_snapshot(request, _amap_client()), args.output)


def command_evaluate(args: argparse.Namespace) -> None:
    _emit(evaluate_itinerary(_read_json(args.input)), args.output)


def command_compile_research(args: argparse.Namespace) -> None:
    _emit(compile_destination_brief(_read_json(args.input)), args.output)


def command_normalize_rail(args: argparse.Namespace) -> None:
    report = normalize_query_result(_read_json(args.input))
    if args.select:
        report["trains"] = select_trains(
            report["trains"],
            seat_class=args.seat_class,
            earliest_departure=args.earliest,
            latest_departure=args.latest,
            max_duration_minutes=args.max_duration,
            require_seat=not args.include_sold_out,
            limit=args.limit,
        )
        report["count"] = len(report["trains"])
    _emit(report, args.output)


def command_validate_flights(args: argparse.Namespace) -> None:
    payload = _read_json(args.input)
    offers = payload if isinstance(payload, list) else payload.get("flight_offers") or []
    now = None if args.skip_freshness else (
        _parse_datetime(args.now) if args.now else datetime.now(timezone.utc)
    )
    report = validate_offers(offers, now=now, max_age_hours=args.max_age_hours)
    _emit(report, args.output)
    if report["status"] == "INVALID":
        raise SystemExit(2)


def command_validate_lodging(args: argparse.Namespace) -> None:
    payload = _read_json(args.input)
    offers = payload if isinstance(payload, list) else payload.get("lodging_offers") or []
    now = None if args.skip_freshness else (
        _parse_datetime(args.now) if args.now else datetime.now(timezone.utc)
    )
    report = validate_lodging(
        offers, now=now, max_age_hours=args.max_age_hours, rooms=args.rooms
    )
    _emit(report, args.output)
    if report["status"] == "INVALID":
        raise SystemExit(2)


def command_validate_plan(args: argparse.Namespace) -> None:
    report = validate_plan_content(_read_json(args.input))
    _emit(report, args.output)
    if report["status"] == "INVALID":
        raise SystemExit(2)
    if report["status"] == "INCOMPLETE_EVIDENCE":
        # Distinct and still non-zero: a partial plan is a real outcome, but
        # it must never be mistaken for a complete one.
        raise SystemExit(3)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only travel planner tools with live Amap data"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    credential_status = subparsers.add_parser(
        "credential-status", help="Check whether the Amap key is configured"
    )
    credential_status.set_defaults(func=command_credential_status)

    preflight = subparsers.add_parser(
        "preflight", help="Verify the configured Amap key with a live request"
    )
    preflight.set_defaults(func=command_preflight)

    doctor = subparsers.add_parser(
        "doctor",
        help="Check Python, Amap, rail MCP, and browser readiness",
    )
    doctor.add_argument(
        "--live",
        action="store_true",
        help="Send a live Amap request when the credential is configured",
    )
    doctor.add_argument(
        "--client",
        choices=("auto", "codex", "claude-code", "generic"),
        default="auto",
        help="Which Agent client to check MCP registration in",
    )
    doctor.add_argument(
        "--browser-status",
        choices=("available", "unavailable", "unknown"),
        default="unknown",
        help="Report the browser capability observed by the invoking Agent",
    )
    doctor.set_defaults(func=command_doctor)

    validate_request = subparsers.add_parser(
        "validate-request",
        help="Validate intake completeness and detect explicit requirement conflicts",
    )
    validate_request.add_argument("--input", required=True)
    validate_request.add_argument("--output")
    validate_request.set_defaults(func=command_validate_request)

    search_places = subparsers.add_parser(
        "search-places", help="Search live Amap POI data"
    )
    search_places.add_argument("--keywords", required=True)
    search_places.add_argument("--city")
    search_places.add_argument("--limit", type=int, default=10)
    search_places.set_defaults(func=command_search_places)

    amap_snapshot = subparsers.add_parser(
        "amap-snapshot", help="Collect live locations, routes, and nearby POIs"
    )
    amap_snapshot.add_argument("--input", required=True)
    amap_snapshot.add_argument("--output")
    amap_snapshot.set_defaults(func=command_amap_snapshot)

    evaluate = subparsers.add_parser(
        "evaluate", help="Evaluate a normalized itinerary JSON file"
    )
    evaluate.add_argument("--input", required=True)
    evaluate.add_argument("--output")
    evaluate.set_defaults(func=command_evaluate)

    compile_research = subparsers.add_parser(
        "compile-research",
        help="Compile normalized social notes into attraction cards",
    )
    compile_research.add_argument("--input", required=True)
    compile_research.add_argument("--output")
    compile_research.set_defaults(func=command_compile_research)

    normalize_rail = subparsers.add_parser(
        "normalize-rail",
        help="Normalize a 12306 query-tickets payload into comparable records",
    )
    normalize_rail.add_argument("--input", required=True)
    normalize_rail.add_argument("--output")
    normalize_rail.add_argument(
        "--select", action="store_true", help="Also narrow to usable candidates"
    )
    normalize_rail.add_argument("--seat-class", dest="seat_class")
    normalize_rail.add_argument("--earliest", help="Earliest departure, HH:MM")
    normalize_rail.add_argument("--latest", help="Latest departure, HH:MM")
    normalize_rail.add_argument("--max-duration", type=int, dest="max_duration")
    normalize_rail.add_argument("--limit", type=int, default=10)
    normalize_rail.add_argument(
        "--include-sold-out", action="store_true", dest="include_sold_out"
    )
    normalize_rail.set_defaults(func=command_normalize_rail)

    validate_flights = subparsers.add_parser(
        "validate-flights",
        help="Check browser-derived flight offers, including price freshness",
    )
    validate_flights.add_argument("--input", required=True)
    validate_flights.add_argument("--output")
    validate_flights.add_argument(
        "--now",
        help="ISO timestamp with offset to check freshness against (default: now)",
    )
    validate_flights.add_argument(
        "--max-age-hours", type=int, default=DEFAULT_MAX_AGE_HOURS,
        dest="max_age_hours",
        help="Age above which a fare must be looked up again (default: 2)",
    )
    validate_flights.add_argument(
        "--skip-freshness", action="store_true", dest="skip_freshness",
        help="Run structural checks only, without comparing against the clock",
    )
    validate_flights.set_defaults(func=command_validate_flights)

    validate_lodging_parser = subparsers.add_parser(
        "validate-lodging",
        help="Check browser-derived lodging offers and derive stay totals",
    )
    validate_lodging_parser.add_argument("--input", required=True)
    validate_lodging_parser.add_argument("--output")
    validate_lodging_parser.add_argument("--rooms", type=int, default=1)
    validate_lodging_parser.add_argument(
        "--max-age-hours", type=int, default=12, dest="max_age_hours"
    )
    validate_lodging_parser.add_argument("--now")
    validate_lodging_parser.add_argument(
        "--skip-freshness", action="store_true", dest="skip_freshness"
    )
    validate_lodging_parser.set_defaults(func=command_validate_lodging)

    validate_plan = subparsers.add_parser(
        "validate-plan",
        help="Validate itinerary content completeness before presentation",
    )
    validate_plan.add_argument("--input", required=True)
    validate_plan.add_argument("--output")
    validate_plan.set_defaults(func=command_validate_plan)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (CredentialError, AmapError, OSError, ValueError, json.JSONDecodeError) as exc:
        _emit(
            {
                "status": "ERROR",
                "error_type": exc.__class__.__name__,
                "message": str(exc),
            }
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
