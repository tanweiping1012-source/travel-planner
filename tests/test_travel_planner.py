from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "src"))

from travel_planner.amap import AmapClient, AmapError
from travel_planner.feasibility import evaluate_itinerary
from travel_planner.intake import validate_trip_request
from travel_planner.research import compile_destination_brief, validate_plan_content


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
