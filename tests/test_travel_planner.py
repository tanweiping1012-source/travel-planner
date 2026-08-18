from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "src"))

from travel_planner.amap import AmapClient, AmapError
from travel_planner.credentials import CredentialError, KeychainCredentialStore
from travel_planner.diagnostics import (
    build_doctor_report,
    default_data_dir,
    detect_client,
)
from travel_planner.feasibility import evaluate_itinerary
from travel_planner.flight import (
    FlightDataError,
    offer_to_activity,
    validate_offers,
)
from travel_planner.intake import validate_trip_request
from travel_planner.rail import (
    RailDataError,
    normalize_query_result,
    normalize_seat,
    normalize_train,
    parse_duration,
    select_trains,
    summarize_availability,
    train_category,
    train_to_activity,
)
from travel_planner.research import compile_destination_brief, validate_plan_content
from travel_planner.timeutil import parse_datetime, require_aware


class FakeAmapTransport:
    def __call__(self, path, params):
        if path == "/v3/geocode/geo":
            return {
                "status": "1",
                "geocodes": [
                    {
                        "formatted_address": "北京市东城区天安门广场",
                        "location": "116.397499,39.908722",
                        "city": "北京市",
                    }
                ],
            }
        if path == "/v3/place/text":
            return {
                "status": "1",
                "pois": [
                    {
                        "id": "CLOSED",
                        "name": "天安门广场(暂停开放)",
                        "location": "116.390000,39.900000",
                        "cityname": "北京市",
                        "address": "测试地址",
                        "type": "风景名胜",
                        "biz_ext": {"rating": "5.0"},
                    },
                    {
                        "id": "B000A",
                        "name": "天安门广场",
                        "location": "116.397499,39.908722",
                        "cityname": "北京市",
                        "address": "东长安街",
                        "type": "风景名胜",
                        "biz_ext": {"rating": "4.8"},
                    }
                ],
            }
        if path == "/v3/place/around":
            return {"status": "1", "pois": []}
        if path == "/v3/direction/walking":
            return {
                "status": "1",
                "route": {"paths": [{"duration": "900", "distance": "1200"}]},
            }
        return {"status": "0", "info": "INVALID_PARAMS", "infocode": "10001"}


class AmapClientTest(unittest.TestCase):
    def setUp(self):
        self.client = AmapClient("not-a-real-secret", transport=FakeAmapTransport())

    def test_geocode_and_place_normalization(self):
        location = self.client.geocode("天安门", "北京")
        places = self.client.search_places("天安门", "北京", 1)
        self.assertEqual(location.city, "北京市")
        self.assertEqual(places[1].name, "天安门广场")
        self.assertEqual(places[1].rating, 4.8)

    def test_route_normalization(self):
        origin = self.client.geocode("天安门", "北京")
        route = self.client.route(origin, origin, "walking")
        self.assertEqual(route.duration_minutes, 15)
        self.assertEqual(route.walking_distance_meters, 1200)

    def test_resolve_location_prefers_named_poi(self):
        location = self.client.resolve_location("天安门广场", "北京")
        self.assertEqual(location.name, "天安门广场")
        self.assertEqual(location.longitude, 116.397499)

    def test_provider_error_does_not_contain_key(self):
        with self.assertRaises(AmapError) as context:
            self.client.route(
                self.client.geocode("天安门", "北京"),
                self.client.geocode("天安门", "北京"),
                "driving",
            )
        self.assertNotIn("not-a-real-secret", str(context.exception))


class CredentialStoreTest(unittest.TestCase):
    def test_environment_value_takes_precedence_without_exposing_it(self):
        def unexpected_runner(*_args, **_kwargs):
            raise AssertionError("Keychain must not run when AMAP_API_KEY is set")

        store = KeychainCredentialStore(
            environment={"AMAP_API_KEY": "environment-secret"},
            command_runner=unexpected_runner,
        )
        self.assertEqual(store.get("amap"), "environment-secret")
        status = store.status("amap")
        self.assertEqual(status["source"], "environment")
        self.assertNotIn("environment-secret", str(status))

    def test_primary_keychain_service_is_used(self):
        def runner(args, **_kwargs):
            service = args[args.index("-s") + 1]
            self.assertEqual(service, "travel-planner-mvp")
            return SimpleNamespace(stdout="primary-secret\n", returncode=0)

        store = KeychainCredentialStore(environment={}, command_runner=runner)
        value, source = store.get_with_source("amap")
        self.assertEqual(value, "primary-secret")
        self.assertEqual(source, "macos-keychain")

    def test_legacy_keychain_service_remains_compatible(self):
        services = []

        def runner(args, **_kwargs):
            service = args[args.index("-s") + 1]
            services.append(service)
            if service == "trae-travel-planner":
                return SimpleNamespace(stdout="legacy-secret\n", returncode=0)
            raise subprocess.CalledProcessError(44, args)

        store = KeychainCredentialStore(environment={}, command_runner=runner)
        value, source = store.get_with_source("amap")
        self.assertEqual(value, "legacy-secret")
        self.assertEqual(source, "macos-keychain-legacy")
        self.assertEqual(
            services,
            ["travel-planner-mvp", "trae-travel-planner"],
        )

    def test_missing_key_is_reported_without_provider_details(self):
        def runner(args, **_kwargs):
            raise subprocess.CalledProcessError(44, args)

        store = KeychainCredentialStore(environment={}, command_runner=runner)
        with self.assertRaises(CredentialError) as context:
            store.get("amap")
        self.assertEqual(str(context.exception), "Amap API key is not configured")


class DiagnosticsTest(unittest.TestCase):
    def test_default_data_dir_is_platform_specific(self):
        home = Path("/test/home")
        self.assertEqual(
            default_data_dir(environment={}, system_name="Darwin", home=home),
            home / "Library" / "Application Support" / "travel-planner-mvp",
        )
        self.assertEqual(
            default_data_dir(environment={}, system_name="Linux", home=home),
            home / ".local" / "share" / "travel-planner-mvp",
        )

    def test_data_dir_override_must_be_absolute(self):
        with self.assertRaisesRegex(ValueError, "must be an absolute path"):
            default_data_dir(
                environment={"TRAVEL_PLANNER_DATA_DIR": "relative/path"},
                system_name="Linux",
                home=Path("/test/home"),
            )

    def rail_runtime(self, data_dir):
        checkout = Path(data_dir) / "mcp-server-12306"
        (checkout / ".venv").mkdir(parents=True)
        (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

    def test_detect_client_prefers_explicit_environment_markers(self):
        self.assertEqual(
            detect_client({"CLAUDECODE": "1"}, command_finder=lambda _c: None),
            "claude-code",
        )
        self.assertEqual(
            detect_client({"CODEX_HOME": "/x"}, command_finder=lambda _c: None),
            "codex",
        )

    def test_detect_client_falls_back_to_an_installed_codex(self):
        self.assertEqual(
            detect_client({}, command_finder=lambda c: "/usr/bin/codex" if c == "codex" else None),
            "codex",
        )

    def test_claude_code_registration_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory)
            self.rail_runtime(data_dir)
            config = data_dir / "claude.json"
            config.write_text(
                json.dumps({"mcpServers": {"12306": {"command": "uv"}}}),
                encoding="utf-8",
            )
            report = build_doctor_report(
                {"provider": "amap", "status": "READY"},
                data_dir=data_dir,
                browser_status="available",
                client="claude-code",
                claude_config_path=config,
            )
        self.assertEqual(report["client"], "claude-code")
        self.assertEqual(report["rail_mcp"]["registration"]["status"], "READY")
        self.assertEqual(report["status"], "READY")

    def test_claude_code_without_the_server_reports_missing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory)
            self.rail_runtime(data_dir)
            config = data_dir / "claude.json"
            config.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
            report = build_doctor_report(
                {"provider": "amap", "status": "READY"},
                data_dir=data_dir,
                client="claude-code",
                claude_config_path=config,
            )
        self.assertEqual(report["rail_mcp"]["registration"]["status"], "MISSING")
        self.assertEqual(report["rail_mcp"]["status"], "PARTIAL")
        self.assertIn(
            "Register the installed 12306 stdio MCP in Claude Code.", report["actions"]
        )

    def test_unreadable_claude_config_is_unverified_not_missing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory)
            self.rail_runtime(data_dir)
            config = data_dir / "claude.json"
            config.write_text("{ not json", encoding="utf-8")
            report = build_doctor_report(
                {"provider": "amap", "status": "READY"},
                data_dir=data_dir,
                client="claude-code",
                claude_config_path=config,
            )
        self.assertEqual(report["rail_mcp"]["registration"]["status"], "UNVERIFIED")

    def test_doctor_report_never_echoes_the_client_config(self):
        """The config holds unrelated account state; only presence may be read."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory)
            self.rail_runtime(data_dir)
            config = data_dir / "claude.json"
            config.write_text(
                json.dumps(
                    {
                        "mcpServers": {"12306": {"env": {"TOKEN": "super-secret"}}},
                        "oauthAccount": {"emailAddress": "user@example.com"},
                    }
                ),
                encoding="utf-8",
            )
            report = build_doctor_report(
                {"provider": "amap", "status": "READY"},
                data_dir=data_dir,
                client="claude-code",
                claude_config_path=config,
            )
        serialized = json.dumps(report)
        self.assertNotIn("super-secret", serialized)
        self.assertNotIn("user@example.com", serialized)

    def test_doctor_reports_ready_capabilities(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory)
            checkout = data_dir / "mcp-server-12306"
            (checkout / ".venv").mkdir(parents=True)
            (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

            report = build_doctor_report(
                {"provider": "amap", "status": "READY"},
                data_dir=data_dir,
                browser_status="available",
                client="codex",
                command_finder=lambda command: "/usr/bin/codex"
                if command == "codex"
                else None,
                command_runner=lambda *_args, **_kwargs: SimpleNamespace(
                    returncode=0
                ),
            )

        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["rail_mcp"]["status"], "READY")
        self.assertEqual(report["browser"]["status"], "AVAILABLE")
        self.assertEqual(report["actions"], [])

    def test_doctor_explains_missing_optional_capabilities(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            report = build_doctor_report(
                {"provider": "amap", "status": "MISSING"},
                data_dir=Path(temporary_directory),
                browser_status="unknown",
                client="codex",
                command_finder=lambda _command: None,
            )

        self.assertEqual(report["status"], "NOT_READY")
        self.assertEqual(report["rail_mcp"]["status"], "MISSING")
        self.assertEqual(report["browser"]["status"], "UNVERIFIED")
        self.assertTrue(report["actions"])


class FeasibilityTest(unittest.TestCase):
    def test_feasible_itinerary(self):
        report = evaluate_itinerary(
            {
                "budget_cny": 500,
                "constraints": {"default_transfer_buffer_minutes": 15},
                "activities": [
                    {
                        "id": "a",
                        "name": "景点A",
                        "start": "2026-10-01T09:00:00+08:00",
                        "end": "2026-10-01T10:00:00+08:00",
                        "estimated_cost": 50,
                    },
                    {
                        "id": "b",
                        "name": "景点B",
                        "start": "2026-10-01T11:00:00+08:00",
                        "end": "2026-10-01T12:00:00+08:00",
                        "estimated_cost": 30,
                    },
                ],
                "segments": [
                    {
                        "from_id": "a",
                        "to_id": "b",
                        "duration_minutes": 30,
                        "buffer_minutes": 15,
                        "estimated_cost": 5,
                    }
                ],
            },
            now=datetime(2026, 10, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(report["status"], "FEASIBLE")
        self.assertEqual(report["summary"]["estimated_cost_cny"], 85)

    def test_transfer_shortage_is_hard_conflict(self):
        report = evaluate_itinerary(
            {
                "activities": [
                    {
                        "id": "a",
                        "name": "景点A",
                        "start": "2026-10-01T09:00:00+08:00",
                        "end": "2026-10-01T10:00:00+08:00",
                    },
                    {
                        "id": "train",
                        "name": "火车",
                        "type": "TRAIN",
                        "start": "2026-10-01T11:00:00+08:00",
                        "end": "2026-10-01T13:00:00+08:00",
                    },
                ],
                "segments": [
                    {
                        "from_id": "a",
                        "to_id": "train",
                        "duration_minutes": 40,
                    }
                ],
            }
        )
        self.assertEqual(report["status"], "INFEASIBLE")
        self.assertEqual(
            report["hard_conflicts"][0]["code"], "INSUFFICIENT_TRANSFER_TIME"
        )

    def test_opening_hours_and_budget_warnings(self):
        report = evaluate_itinerary(
            {
                "budget_cny": 100,
                "activities": [
                    {
                        "id": "museum",
                        "name": "博物馆",
                        "start": "2026-10-01T16:30:00+08:00",
                        "end": "2026-10-01T18:00:00+08:00",
                        "last_entry_time": "16:00",
                        "closing_time": "17:00",
                        "estimated_cost": 150,
                    }
                ],
            }
        )
        codes = {issue["code"] for issue in report["hard_conflicts"]}
        self.assertIn("AFTER_LAST_ENTRY", codes)
        self.assertIn("AFTER_CLOSING", codes)
        self.assertEqual(report["warnings"][0]["code"], "BUDGET_EXCEEDED")

    def visit(self, start, end, **extra):
        activity = {
            "id": "lingyin",
            "name": "灵隐寺",
            "type": "ATTRACTION",
            "start": start,
            "end": end,
            "opening_time": "07:00",
            "closing_time": "18:00",
        }
        activity.update(extra)
        return {"activities": [activity], "segments": []}

    def test_utc_and_offset_notation_agree_when_zone_is_declared(self):
        """The same instant must evaluate the same however it is written."""

        as_offset = evaluate_itinerary(
            self.visit("2026-10-01T09:00:00+08:00", "2026-10-01T11:00:00+08:00")
        )
        as_utc = evaluate_itinerary(
            {
                **self.visit("2026-10-01T01:00:00Z", "2026-10-01T03:00:00Z"),
                "timezone": "Asia/Shanghai",
            }
        )
        self.assertEqual(as_offset["status"], "FEASIBLE")
        self.assertEqual(as_utc["status"], "FEASIBLE")

    def test_utc_without_declared_zone_warns_instead_of_blocking(self):
        report = evaluate_itinerary(
            self.visit("2026-10-01T01:00:00Z", "2026-10-01T03:00:00Z")
        )
        codes = {issue["code"] for issue in report["warnings"]}
        self.assertIn("AMBIGUOUS_TIMEZONE", codes)
        self.assertEqual(report["hard_conflicts"], [])

    def test_per_activity_zone_overrides_the_trip_zone(self):
        report = evaluate_itinerary(
            {
                "timezone": "Asia/Shanghai",
                "activities": [
                    {
                        "id": "sensoji",
                        "name": "浅草寺",
                        "timezone": "Asia/Tokyo",
                        "start": "2026-10-01T09:00:00+09:00",
                        "end": "2026-10-01T11:00:00+09:00",
                        "opening_time": "06:00",
                        "closing_time": "17:00",
                    }
                ],
            }
        )
        self.assertEqual(report["status"], "FEASIBLE")

    def test_overnight_break_is_not_a_missing_transit_segment(self):
        report = evaluate_itinerary(
            {
                "activities": [
                    {
                        "id": f"day{day}",
                        "name": f"第{day}天",
                        "start": f"2026-10-0{day}T09:00:00+08:00",
                        "end": f"2026-10-0{day}T17:00:00+08:00",
                    }
                    for day in range(1, 5)
                ],
                "segments": [],
            }
        )
        self.assertEqual(report["status"], "FEASIBLE")
        self.assertEqual(report["score"], 100)

    def test_declared_overnight_segment_is_still_checked(self):
        report = evaluate_itinerary(
            {
                "activities": [
                    {
                        "id": "hotel",
                        "name": "酒店退房",
                        "start": "2026-10-01T20:00:00+08:00",
                        "end": "2026-10-01T21:50:00+08:00",
                    },
                    {
                        "id": "night-train",
                        "name": "夜班火车",
                        "type": "TRAIN",
                        "start": "2026-10-01T22:00:00+08:00",
                        "end": "2026-10-02T07:00:00+08:00",
                    },
                ],
                "segments": [
                    {"from_id": "hotel", "to_id": "night-train", "duration_minutes": 40}
                ],
            }
        )
        self.assertEqual(report["status"], "INFEASIBLE")
        self.assertEqual(
            report["hard_conflicts"][0]["code"], "INSUFFICIENT_TRANSFER_TIME"
        )

    def test_explicit_zero_buffer_is_not_replaced_by_a_default(self):
        report = evaluate_itinerary(
            {
                "constraints": {"default_transfer_buffer_minutes": 60},
                "activities": [
                    {
                        "id": "a",
                        "name": "景点A",
                        "start": "2026-10-01T09:00:00+08:00",
                        "end": "2026-10-01T10:00:00+08:00",
                    },
                    {
                        "id": "b",
                        "name": "景点B",
                        "start": "2026-10-01T10:30:00+08:00",
                        "end": "2026-10-01T11:30:00+08:00",
                    },
                ],
                "segments": [
                    {
                        "from_id": "a",
                        "to_id": "b",
                        "duration_minutes": 30,
                        "buffer_minutes": 0,
                    }
                ],
            }
        )
        self.assertEqual(report["status"], "FEASIBLE")

    def test_malformed_opening_time_warns_instead_of_crashing(self):
        report = evaluate_itinerary(
            self.visit(
                "2026-10-01T09:00:00+08:00",
                "2026-10-01T11:00:00+08:00",
                opening_time="上午九点",
            )
        )
        codes = {issue["code"] for issue in report["warnings"]}
        self.assertIn("INVALID_TIME_FORMAT", codes)

    def test_blocked_plan_never_outranks_a_merely_risky_one(self):
        blocked = evaluate_itinerary(
            {
                "activities": [
                    {
                        "id": "a",
                        "name": "景点A",
                        "start": "2026-10-01T09:00:00+08:00",
                        "end": "2026-10-01T10:00:00+08:00",
                    },
                    {
                        "id": "b",
                        "name": "火车",
                        "type": "TRAIN",
                        "start": "2026-10-01T10:10:00+08:00",
                        "end": "2026-10-01T12:00:00+08:00",
                    },
                ],
                "segments": [
                    {"from_id": "a", "to_id": "b", "duration_minutes": 40}
                ],
            }
        )
        risky = evaluate_itinerary(
            {
                "budget_cny": 1,
                "activities": [
                    {
                        "id": f"w{day}",
                        "name": f"景点{day}",
                        "start": f"2026-10-0{day}T09:00:00+08:00",
                        "end": f"2026-10-0{day}T10:00:00+08:00",
                        "estimated_cost": 100,
                    }
                    for day in range(1, 5)
                ],
                "segments": [],
            }
        )
        self.assertEqual(blocked["status"], "INFEASIBLE")
        self.assertEqual(risky["status"], "FEASIBLE_WITH_RISK")
        self.assertLess(blocked["score"], risky["score"])


class CommandLineInterfaceTest(unittest.TestCase):
    """The CLI is a script, so it is loaded by path rather than imported."""

    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "travel_planner_cli", SKILL_ROOT / "scripts" / "travel_planner.py"
        )
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)

    def subcommands(self):
        parser = self.cli.build_parser()
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                return action.choices
        raise AssertionError("no subparsers found")

    def test_no_subcommand_is_registered_twice(self):
        """Count registrations, not the resulting names.

        A duplicate is silently overwritten on 3.9 and 3.10 and raises
        ArgumentError from 3.11, so the same bug is invisible on one
        interpreter and fatal on another. Inspecting the parser afterwards
        cannot see it either — the names live in a dict, which cannot hold a
        duplicate key — so the registration calls themselves are recorded.
        """

        registered = []
        original = argparse._SubParsersAction.add_parser

        def recording(action_self, name, **kwargs):
            registered.append(name)
            return original(action_self, name, **kwargs)

        argparse._SubParsersAction.add_parser = recording
        try:
            self.cli.build_parser()
        finally:
            argparse._SubParsersAction.add_parser = original

        duplicates = sorted(
            {name for name in registered if registered.count(name) > 1}
        )
        self.assertEqual(duplicates, [], f"registered more than once: {duplicates}")

    def test_every_subcommand_has_a_handler(self):
        for name, sub in self.subcommands().items():
            self.assertTrue(
                callable(sub.get_default("func")), f"{name} has no handler"
            )

    def test_declared_options_reach_their_handler(self):
        """A flag the parser accepts but the handler ignores fails silently."""

        import inspect

        for name, sub in self.subcommands().items():
            source = inspect.getsource(sub.get_default("func"))
            for action in sub._actions:
                if action.dest in {"help", "output"} or not action.option_strings:
                    continue
                # Match args.<dest>, not the bare name: a dest such as "now"
                # occurs as a substring of datetime.now and would pass on its
                # own while the flag is in fact ignored.
                self.assertIn(
                    f"args.{action.dest}",
                    source,
                    f"{name} accepts --{action.dest.replace('_', '-')} "
                    "but its handler never reads it",
                )

    def test_validate_flights_accepts_an_explicit_clock(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(
            ["validate-flights", "--input", "x.json", "--now", "2026-08-18T15:00:00+08:00"]
        )
        self.assertEqual(args.now, "2026-08-18T15:00:00+08:00")
        self.assertFalse(args.skip_freshness)

    def test_naive_clock_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone offset"):
            self.cli._parse_datetime("2026-08-18T15:00:00")


class FlightOfferTest(unittest.TestCase):
    def offer(self, **overrides):
        offer = {
            "offer_id": "ctrip-1",
            "mode": "flight",
            "outbound": {
                "carrier": "示例航空",
                "flight_number": "EX1234",
                "origin_airport": "CAN",
                "destination_airport": "KWL",
                "departure": "2026-10-01T07:50:00+08:00",
                "arrival": "2026-10-01T09:10:00+08:00",
                "duration_minutes": 80,
                "stops": 0,
            },
            "displayed_total_price": 620,
            "currency": "CNY",
            "baggage_visibility": "CHECKED_20KG",
            "final_price_guaranteed": False,
            "source": {
                "channel": "ctrip_web",
                "checked_at": "2026-10-01T06:00:00+08:00",
            },
        }
        offer.update(overrides)
        return offer

    def test_freshness_is_skipped_without_a_clock(self):
        """A stored plan is not necessarily a plan being presented."""

        report = validate_offers([self.offer()])
        self.assertFalse(report["summary"]["freshness_checked"])
        codes = {issue["code"] for issue in report["warnings"]}
        self.assertNotIn("STALE_FLIGHT_PRICE", codes)

    def test_stale_price_is_flagged_when_a_clock_is_given(self):
        report = validate_offers(
            [self.offer()],
            now=datetime(2026, 10, 1, 12, 0, tzinfo=timezone(timedelta(hours=8))),
        )
        stale = [i for i in report["warnings"] if i["code"] == "STALE_FLIGHT_PRICE"]
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["details"]["age_hours"], 6.0)

    def test_fresh_price_within_the_window_passes(self):
        report = validate_offers(
            [self.offer()],
            now=datetime(2026, 10, 1, 7, 0, tzinfo=timezone(timedelta(hours=8))),
        )
        codes = {issue["code"] for issue in report["warnings"]}
        self.assertNotIn("STALE_FLIGHT_PRICE", codes)

    def test_unguaranteed_price_must_be_surfaced(self):
        report = validate_offers([self.offer()])
        codes = {issue["code"] for issue in report["warnings"]}
        self.assertIn("PRICE_NOT_GUARANTEED", codes)

    def test_duration_inconsistent_with_the_clock_is_flagged(self):
        offer = self.offer()
        offer["outbound"]["duration_minutes"] = 200
        report = validate_offers([offer])
        mismatch = [i for i in report["warnings"] if i["code"] == "DURATION_MISMATCH"]
        self.assertEqual(mismatch[0]["details"], {"stated": 200, "implied": 80})

    def test_small_duration_difference_is_tolerated(self):
        offer = self.offer()
        offer["outbound"]["duration_minutes"] = 83
        report = validate_offers([offer])
        codes = {issue["code"] for issue in report["warnings"]}
        self.assertNotIn("DURATION_MISMATCH", codes)

    def test_arrival_before_departure_is_a_hard_conflict(self):
        offer = self.offer()
        offer["outbound"]["arrival"] = "2026-10-01T07:00:00+08:00"
        report = validate_offers([offer])
        self.assertEqual(report["status"], "INVALID")
        self.assertEqual(
            report["hard_conflicts"][0]["code"], "ARRIVAL_BEFORE_DEPARTURE"
        )

    def test_missing_channel_or_timestamp_is_a_hard_conflict(self):
        report = validate_offers([self.offer(source={"channel": "ctrip_web"})])
        self.assertEqual(report["status"], "INVALID")
        self.assertEqual(
            report["hard_conflicts"][0]["code"], "MISSING_SOURCE_METADATA"
        )

    def test_unparseable_leg_does_not_crash_the_run(self):
        offer = self.offer()
        offer["outbound"]["departure"] = "明天早上"
        report = validate_offers([offer])
        self.assertEqual(report["hard_conflicts"][0]["code"], "INVALID_FLIGHT_LEG")

    def test_return_leg_is_checked_too(self):
        offer = self.offer()
        offer["return"] = {
            "flight_number": "EX1235",
            "origin_airport": "KWL",
            "destination_airport": "CAN",
            "departure": "2026-10-05T20:00:00+08:00",
            "arrival": "2026-10-05T19:00:00+08:00",
        }
        report = validate_offers([offer])
        self.assertEqual(report["summary"]["leg_count"], 2)
        self.assertEqual(
            report["hard_conflicts"][0]["code"], "ARRIVAL_BEFORE_DEPARTURE"
        )

    def test_activity_carries_the_gate_buffer_and_price_provenance(self):
        activity = offer_to_activity(self.offer(), activity_id="fl-1")
        self.assertEqual(activity["type"], "FLIGHT_DOMESTIC")
        self.assertEqual(activity["required_buffer_minutes"], 120)
        self.assertEqual(activity["estimated_cost"], 620.0)
        self.assertFalse(activity["price_is_final"])
        self.assertEqual(activity["source_checked_at"], "2026-10-01T06:00:00+08:00")

    def test_international_activity_uses_the_longer_buffer(self):
        activity = offer_to_activity(self.offer(), international=True)
        self.assertEqual(activity["type"], "FLIGHT_INTERNATIONAL")
        self.assertEqual(activity["required_buffer_minutes"], 180)

    def test_activity_requires_the_requested_leg(self):
        with self.assertRaises(FlightDataError):
            offer_to_activity(self.offer(), leg="return")

    def test_activity_feeds_the_feasibility_checker(self):
        """A flight is an activity; reaching the airport is the segment."""

        activity = offer_to_activity(self.offer(), activity_id="flight")
        report = evaluate_itinerary(
            {
                "timezone": "Asia/Shanghai",
                "activities": [
                    {
                        "id": "hotel",
                        "name": "酒店退房",
                        "start": "2026-10-01T04:30:00+08:00",
                        "end": "2026-10-01T05:00:00+08:00",
                    },
                    activity,
                ],
                "segments": [
                    {"from_id": "hotel", "to_id": "flight", "duration_minutes": 45}
                ],
            }
        )
        self.assertEqual(report["status"], "FEASIBLE")

    def test_late_hotel_checkout_misses_the_gate(self):
        activity = offer_to_activity(self.offer(), activity_id="flight")
        report = evaluate_itinerary(
            {
                "timezone": "Asia/Shanghai",
                "activities": [
                    {
                        "id": "hotel",
                        "name": "酒店退房",
                        "start": "2026-10-01T05:00:00+08:00",
                        "end": "2026-10-01T06:30:00+08:00",
                    },
                    activity,
                ],
                "segments": [
                    {"from_id": "hotel", "to_id": "flight", "duration_minutes": 45}
                ],
            }
        )
        # 80 minutes available, but 45 travel + 120 gate buffer are required.
        self.assertEqual(report["status"], "INFEASIBLE")
        self.assertEqual(
            report["hard_conflicts"][0]["code"], "INSUFFICIENT_TRANSFER_TIME"
        )


class RailNormalizationTest(unittest.TestCase):
    def train(self, **overrides):
        train = {
            "train_no": "G1321",
            "from_station": "上海虹桥",
            "from_station_code": "AOH",
            "to_station": "杭州东",
            "to_station_code": "HGH",
            "start_time": "06:07",
            "arrive_time": "06:56",
            "duration": "00:49",
            "seats": {
                "business": "9",
                "first_class": "有",
                "second_class": "有",
                "no_seat": "无",
            },
        }
        train.update(overrides)
        return train

    def test_seat_words_and_counts_become_comparable(self):
        """12306 mixes integers with 有/无 in one field."""

        sold_out = normalize_seat("无")
        limited = normalize_seat("9")
        plenty = normalize_seat("有")

        self.assertEqual(sold_out["status"], "SOLD_OUT")
        self.assertEqual(sold_out["at_least"], 0)
        self.assertEqual(limited["status"], "LIMITED")
        self.assertEqual(limited["count"], 9)
        self.assertEqual(plenty["status"], "AVAILABLE")
        self.assertIsNone(plenty["count"])
        # 有 has no exact count but is still known to beat any exact count.
        self.assertGreater(plenty["at_least"], limited["at_least"])

    def test_unknown_seat_value_does_not_raise(self):
        seat = normalize_seat("候补")
        self.assertEqual(seat["status"], "UNKNOWN")
        self.assertEqual(seat["at_least"], 0)

    def test_zero_count_is_treated_as_sold_out(self):
        self.assertEqual(normalize_seat("0")["status"], "SOLD_OUT")

    def test_parse_duration_and_category(self):
        self.assertEqual(parse_duration("01:42"), 102)
        self.assertIsNone(parse_duration("待定"))
        self.assertEqual(train_category("G1321"), "高铁")
        self.assertEqual(train_category("Z175"), "直达特快")
        self.assertEqual(train_category("1461"), "普速")

    def test_normalize_train_ranks_bookable_classes_by_comfort(self):
        train = normalize_train(self.train())
        self.assertEqual(train["duration_minutes"], 49)
        self.assertEqual(train["bookable_classes"][0], "business")
        self.assertTrue(train["has_seat_available"])
        self.assertFalse(train["arrives_next_day"])

    def test_no_seat_alone_does_not_count_as_bookable(self):
        train = normalize_train(
            self.train(seats={"second_class": "无", "no_seat": "有"})
        )
        self.assertEqual(train["bookable_classes"], [])
        self.assertFalse(train["has_seat_available"])

    def test_overnight_train_is_flagged(self):
        train = normalize_train(
            self.train(train_no="Z175", start_time="22:10", arrive_time="07:00",
                       duration="08:50")
        )
        self.assertTrue(train["arrives_next_day"])
        self.assertEqual(train["duration_minutes"], 530)

    def test_malformed_seats_raise_rail_error(self):
        with self.assertRaises(RailDataError):
            normalize_train(self.train(seats="有票"))

    def test_normalize_query_result_requires_trains(self):
        with self.assertRaises(RailDataError):
            normalize_query_result({"success": True})

    def test_select_filters_by_seat_window_and_duration(self):
        payload = {
            "success": True,
            "from_station": "上海",
            "to_station": "杭州",
            "train_date": "2026-08-20",
            "trains": [
                self.train(train_no="G1", start_time="06:00", duration="00:45"),
                self.train(train_no="G2", start_time="09:00", duration="02:30"),
                self.train(train_no="G3", start_time="09:30", duration="00:50"),
                self.train(
                    train_no="G4",
                    start_time="10:00",
                    duration="00:40",
                    seats={"second_class": "无", "no_seat": "无"},
                ),
            ],
        }
        result = normalize_query_result(payload)
        picks = select_trains(
            result["trains"],
            seat_class="second_class",
            earliest_departure="08:00",
            max_duration_minutes=90,
        )
        self.assertEqual([t["train_no"] for t in picks], ["G3"])

    def test_select_sorts_by_duration_then_departure(self):
        payload = {
            "trains": [
                self.train(train_no="slow", duration="02:00", start_time="08:00"),
                self.train(train_no="fast", duration="00:45", start_time="09:00"),
            ]
        }
        picks = select_trains(normalize_query_result(payload)["trains"])
        self.assertEqual([t["train_no"] for t in picks], ["fast", "slow"])

    def test_malformed_leg_raises_this_module_s_error_not_keyerror(self):
        """A bare KeyError is not a ValueError and escapes the CLI handler."""

        for broken in (
            {"outbound": {"departure": "2026-09-01T08:00:00+08:00"}},
            {"outbound": {"flight_number": "MU123"}},
            {"outbound": "not-a-dict"},
        ):
            with self.assertRaises(FlightDataError):
                offer_to_activity(broken)

    def test_activity_omits_price_when_none_was_looked_up(self):
        """query-tickets carries no fare, so none may be invented."""

        train = normalize_train(self.train())
        activity = train_to_activity(train, "2026-08-20", seat_class="second_class")
        self.assertNotIn("estimated_cost", activity)
        self.assertEqual(activity["type"], "TRAIN")
        self.assertEqual(activity["start"], "2026-08-20T06:07:00+08:00")
        self.assertEqual(activity["end"], "2026-08-20T06:56:00+08:00")
        self.assertEqual(activity["required_buffer_minutes"], 45)
        self.assertEqual(activity["seat_class_label"], "二等座")

    def test_activity_records_price_source_when_supplied(self):
        train = normalize_train(self.train())
        activity = train_to_activity(train, "2026-08-20", price_cny=73.0)
        self.assertEqual(activity["estimated_cost"], 73.0)
        self.assertEqual(activity["price_source"], "12306:query-ticket-price")

    def test_overnight_train_activity_ends_on_the_next_day(self):
        train = normalize_train(
            self.train(train_no="Z175", start_time="22:10", arrive_time="07:00",
                       duration="08:50")
        )
        activity = train_to_activity(train, "2026-08-20")
        self.assertEqual(activity["start"], "2026-08-20T22:10:00+08:00")
        self.assertEqual(activity["end"], "2026-08-21T07:00:00+08:00")

    def test_activity_feeds_the_feasibility_checker(self):
        """The train is an activity; the ride to the station is the segment."""

        train = normalize_train(self.train())
        activity = train_to_activity(train, "2026-08-20", activity_id="g1321")
        report = evaluate_itinerary(
            {
                "timezone": "Asia/Shanghai",
                "activities": [
                    {
                        "id": "hotel",
                        "name": "酒店退房",
                        "start": "2026-08-20T04:30:00+08:00",
                        "end": "2026-08-20T05:00:00+08:00",
                    },
                    activity,
                ],
                # 20 minutes by car to the station, from a routing provider.
                "segments": [
                    {"from_id": "hotel", "to_id": "g1321", "duration_minutes": 20}
                ],
            }
        )
        self.assertEqual(report["status"], "FEASIBLE")

    def test_late_departure_from_hotel_misses_the_train(self):
        train = normalize_train(self.train())
        activity = train_to_activity(train, "2026-08-20", activity_id="g1321")
        report = evaluate_itinerary(
            {
                "timezone": "Asia/Shanghai",
                "activities": [
                    {
                        "id": "hotel",
                        "name": "酒店退房",
                        "start": "2026-08-20T05:00:00+08:00",
                        "end": "2026-08-20T05:40:00+08:00",
                    },
                    activity,
                ],
                "segments": [
                    {"from_id": "hotel", "to_id": "g1321", "duration_minutes": 20}
                ],
            }
        )
        # 27 minutes available, but 20 travel + 45 gate buffer are required.
        self.assertEqual(report["status"], "INFEASIBLE")
        self.assertEqual(
            report["hard_conflicts"][0]["code"], "INSUFFICIENT_TRANSFER_TIME"
        )

    def test_activity_requires_a_duration(self):
        train = normalize_train(self.train(duration="待定"))
        with self.assertRaises(RailDataError):
            train_to_activity(train, "2026-08-20")

    def test_activity_rejects_an_invalid_date(self):
        train = normalize_train(self.train())
        with self.assertRaises(RailDataError):
            train_to_activity(train, "2026-13-99")

    def test_summarize_availability_is_human_readable(self):
        text = summarize_availability(normalize_train(self.train()))
        self.assertIn("商务座 9", text)
        self.assertIn("一等座 充足", text)
        self.assertIn("无座 无", text)


class IntakeDefaultsTest(unittest.TestCase):
    """A sentence a traveller would actually say must not become a form."""

    def natural(self, **extra):
        request = {
            "origin": "上海",
            "destination": "杭州",
            "start_date": "2026-09-05",
            "end_date": "2026-09-07",
            "travelers": 2,
            "budget_cny": 2000,
            "style": "balanced",
        }
        request.update(extra)
        return request

    def answerable(self, **extra):
        defaults = {
            "budget_scope": "PER_PERSON",
            "mobility": {"level": "MODERATE"},
            "browser_approval": {
                "xiaohongshu": "ALLOW_MANUAL_LOGIN",
                "ota": "ANONYMOUS_ONLY",
            },
        }
        defaults.update(extra)
        return self.natural(**defaults)

    def test_only_the_materially_ambiguous_fields_are_asked(self):
        """2000 per person is twice 2000 for the party; the rest can default."""

        report = validate_trip_request(self.natural())
        self.assertEqual(
            sorted(report["missing_fields"]),
            ["browser_approval", "budget_scope", "mobility"],
        )

    def test_empty_by_nature_fields_never_block(self):
        """Nobody volunteers that they have no excluded places."""

        report = validate_trip_request(self.answerable())
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["errors"], [])
        for field in ("must_visit", "excluded_places", "tradeoff_priority",
                      "risk_tolerance"):
            self.assertNotIn(field, report["missing_fields"])

    def test_every_default_is_reported_as_an_assumption(self):
        report = validate_trip_request(self.answerable())
        self.assertTrue(report["assumptions"])
        joined = " ".join(report["assumptions"])
        self.assertIn("必去", joined)
        self.assertIn("步行", joined)
        self.assertIn("海拔", joined)

    def test_walking_limit_follows_the_stated_level(self):
        report = validate_trip_request(self.answerable())
        self.assertIn("8", " ".join(report["assumptions"]))
        low = validate_trip_request(
            self.natural(
                budget_scope="PER_PERSON",
                mobility={"level": "LOW"},
                browser_approval={"xiaohongshu": "DENY", "ota": "DENY"},
            )
        )
        self.assertIn("4", " ".join(low["assumptions"]))

    def test_supplied_values_are_not_replaced_by_defaults(self):
        report = validate_trip_request(
            self.answerable(
                must_visit=[{"name": "西湖", "priority": "CORE"}],
                tradeoff_priority=["COST", "CORE_PLACES", "PACE", "COMFORT"],
                mobility={
                    "level": "LOW",
                    "max_walking_km_per_day": 3,
                    "accepts_high_altitude": False,
                },
            )
        )
        self.assertEqual(report["status"], "READY")
        joined = " ".join(report["assumptions"])
        self.assertNotIn("必去", joined)
        self.assertNotIn("步行", joined)
        self.assertNotIn("海拔", joined)

    def test_a_supplied_value_of_the_wrong_type_still_fails(self):
        """Defaulting on absence must not soften validation on presence."""

        report = validate_trip_request(
            self.natural(
                budget_scope="PER_PERSON",
                browser_approval={"xiaohongshu": "DENY", "ota": "DENY"},
                mobility={
                    "level": "MODERATE",
                    "max_walking_km_per_day": -5,
                    "accepts_high_altitude": "yes",
                },
            )
        )
        self.assertEqual(report["status"], "INVALID")
        self.assertEqual(len(report["errors"]), 2)

    def test_the_caller_s_request_object_is_not_mutated(self):
        request = self.answerable()
        validate_trip_request(request)
        self.assertNotIn("must_visit", request)
        self.assertNotIn("tradeoff_priority", request)


class TimeUtilTest(unittest.TestCase):
    def test_naive_clock_is_rejected_with_the_fix_in_the_message(self):
        """datetime.now() is the obvious call and returns a naive value."""

        with self.assertRaises(ValueError) as context:
            require_aware(datetime(2026, 8, 18, 15, 0, 0))
        message = str(context.exception)
        self.assertIn("timezone-aware", message)
        self.assertIn("datetime.now(timezone.utc)", message)

    def test_non_datetime_clock_is_rejected(self):
        with self.assertRaises(ValueError):
            require_aware("2026-08-18T15:00:00+08:00")

    def test_aware_clock_passes_through_unchanged(self):
        moment = datetime(2026, 8, 18, 15, 0, 0, tzinfo=timezone.utc)
        self.assertIs(require_aware(moment), moment)

    def test_z_suffix_is_accepted_on_every_supported_python(self):
        """fromisoformat only learned Z in 3.11; this code supports 3.9."""

        self.assertEqual(
            parse_datetime("2026-08-18T07:00:00Z"),
            datetime(2026, 8, 18, 7, 0, 0, tzinfo=timezone.utc),
        )

    def test_offsetless_value_names_the_field(self):
        with self.assertRaises(ValueError) as context:
            parse_datetime("2026-08-18T15:00:00", field="checked_at")
        self.assertIn("checked_at", str(context.exception))

    def test_both_engines_reject_a_naive_clock(self):
        """A confusing TypeError from inside a subtraction is not an answer."""

        for call in (
            lambda: evaluate_itinerary(
                {"activities": [], "segments": []}, now=datetime(2026, 8, 18, 15)
            ),
            lambda: validate_offers([], now=datetime(2026, 8, 18, 15)),
        ):
            with self.assertRaises(ValueError):
                call()


class IntakeValidationTest(unittest.TestCase):
    def complete_request(self):
        return {
            "origin": "甲城",
            "destination": "乙城与周边",
            "start_date": "2027-04-10",
            "end_date": "2027-04-13",
            "travelers": 2,
            "budget_cny": 3500,
            "budget_scope": "PER_PERSON",
            "style": "balanced",
            "must_visit": [{"name": "核心景点", "priority": "CORE"}],
            "excluded_places": [],
            "mobility": {
                "level": "MODERATE",
                "max_walking_km_per_day": 8,
                "accepts_high_altitude": True,
                "accessibility_needs": [],
            },
            "tradeoff_priority": [
                "CORE_PLACES",
                "COST",
                "PACE",
                "COMFORT",
            ],
            "risk_tolerance": {
                "accepts_weather_dependent_core": True,
            },
            "browser_approval": {
                "xiaohongshu": "ALLOW_MANUAL_LOGIN",
                "ota": "ANONYMOUS_ONLY",
            },
        }

    def test_complete_request_is_ready_without_questions(self):
        report = validate_trip_request(self.complete_request())
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["questions_required"], [])

    def test_missing_fields_are_batched_into_one_question(self):
        report = validate_trip_request(
            {
                "origin": "甲城",
                "destination": "乙城",
                "start_date": "2027-04-10",
                "end_date": "2027-04-13",
            }
        )
        self.assertEqual(report["status"], "NEEDS_CLARIFICATION")
        self.assertIn("travelers", report["missing_fields"])
        self.assertEqual(len(report["questions_required"]), 1)

    def test_required_and_excluded_place_conflict_is_reported(self):
        request = self.complete_request()
        request["excluded_places"] = ["核心景点"]
        report = validate_trip_request(request)
        self.assertEqual(report["status"], "NEEDS_CLARIFICATION")
        self.assertIn("核心景点".casefold(), report["conflicts"][0])

    def test_invalid_date_range_is_rejected(self):
        request = self.complete_request()
        request["end_date"] = "2027-04-09"
        report = validate_trip_request(request)
        self.assertEqual(report["status"], "INVALID")
        self.assertIn(
            "end_date must not be earlier than start_date",
            report["errors"],
        )


class ResearchCompilerTest(unittest.TestCase):
    def test_compiles_attraction_card_from_multiple_notes(self):
        brief = compile_destination_brief(
            {
                "destination": "示例目的地",
                "travel_style": "relaxed",
                "notes": [
                    {
                        "title": "笔记A",
                        "url": "https://example.com/a",
                        "checked_at": "2026-08-10T10:00:00+08:00",
                        "place_evidence": [
                            {
                                "name": "示例景区",
                                "features": ["湖泊与森林"],
                                "why_visit": ["集中体验自然景观"],
                                "suggested_duration_minutes": 360,
                                "best_time": "上午",
                                "physical_load": "中等",
                                "caveats": ["雨天路滑"],
                            }
                        ],
                    },
                    {
                        "title": "笔记B",
                        "url": "https://example.com/b",
                        "checked_at": "2026-08-10T11:00:00+08:00",
                        "place_evidence": [
                            {
                                "name": "示例景区",
                                "features": ["森林与步道"],
                                "why_visit": ["适合单核心一日游"],
                                "suggested_duration_minutes": 420,
                                "caveats": ["接驳需确认"],
                            }
                        ],
                    },
                ],
            }
        )
        card = brief["attraction_cards"][0]
        self.assertEqual(brief["status"], "VALID")
        self.assertEqual(card["suggested_duration_minutes"], 390)
        self.assertEqual(card["evidence_count"], 2)
        self.assertEqual(card["missing_fields"], [])
        self.assertIn("森林与步道", card["features"])

    def test_incomplete_card_is_reported(self):
        brief = compile_destination_brief(
            {
                "destination": "示例目的地",
                "notes": [
                    {
                        "url": "https://example.com/a",
                        "place_evidence": [{"name": "跑马山"}],
                    }
                ],
            }
        )
        self.assertIn("features", brief["attraction_cards"][0]["missing_fields"])
        self.assertTrue(brief["warnings"])


class PlanContentValidationTest(unittest.TestCase):
    def test_rejects_transport_only_plan(self):
        report = validate_plan_content(
            {
                "days": [
                    {
                        "activities": [
                            {
                                "id": "flight",
                                "type": "FLIGHT_DOMESTIC",
                                "name": "甲城飞乙城",
                                "description": "搭乘航班",
                            }
                        ]
                    }
                ]
            }
        )
        self.assertEqual(report["status"], "INVALID")
        self.assertIn("Plan has no attraction activities", report["errors"])

    def test_accepts_descriptive_attraction_plan(self):
        report = validate_plan_content(
            {
                "days": [
                    {
                        "activities": [
                            {
                                "id": "old-town",
                                "type": "ATTRACTION",
                                "name": "示例老城",
                                "description": "沿滨河步道慢走。",
                                "features": ["滨河城市景观"],
                                "why_visit": ["适合低强度游览"],
                                "suggested_duration_minutes": 180,
                                "source_refs": ["source-1"],
                            }
                        ]
                    }
                ],
                "sources": [{"id": "source-1"}],
                "segments": [],
            }
        )
        self.assertEqual(report["status"], "VALID")

    def test_rejects_missing_transition(self):
        report = validate_plan_content(
            {
                "days": [
                    {
                        "activities": [
                            {
                                "id": "a",
                                "type": "ATTRACTION",
                                "name": "景点A",
                                "description": "游览A。",
                                "features": ["特色A"],
                                "why_visit": ["理由A"],
                                "suggested_duration_minutes": 60,
                                "source_refs": ["source-1"],
                            },
                            {
                                "id": "b",
                                "type": "ATTRACTION",
                                "name": "景点B",
                                "description": "游览B。",
                                "features": ["特色B"],
                                "why_visit": ["理由B"],
                                "suggested_duration_minutes": 60,
                                "source_refs": ["source-1"],
                            },
                        ]
                    }
                ],
                "sources": [{"id": "source-1"}],
                "segments": [],
            }
        )
        self.assertEqual(report["status"], "INVALID")
        self.assertIn("Missing transition segment: a -> b", report["errors"])


if __name__ == "__main__":
    unittest.main()
