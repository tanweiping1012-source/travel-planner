"""Compile normalized social research into destination and attraction briefs."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List

from travel_planner.flight import validate_offers


def _strings(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))


def compile_destination_brief(research: Dict[str, Any]) -> dict:
    """Merge place evidence from normalized social notes.

    Browser output must first be normalized into the data contract. This
    function deliberately avoids extracting facts from arbitrary prose.
    """

    notes = research.get("notes") or []
    grouped: Dict[str, List[dict]] = defaultdict(list)
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(notes, list) or not notes:
        return {
            "status": "INVALID",
            "destination": research.get("destination"),
            "attraction_cards": [],
            "errors": ["No normalized social notes were provided"],
            "warnings": [],
        }

    for note_index, note in enumerate(notes):
        if not isinstance(note, dict):
            warnings.append(f"Skipped non-object note at index {note_index}")
            continue
        url = str(note.get("url") or "").strip()
        if not url:
            warnings.append(f"Note {note_index + 1} has no source URL")
        evidence_items = note.get("place_evidence") or []
        if not evidence_items:
            warnings.append(
                f"Note {note_index + 1} has no structured place_evidence"
            )
        for evidence in evidence_items:
            if not isinstance(evidence, dict):
                continue
            name = str(evidence.get("name") or "").strip()
            if not name:
                warnings.append(
                    f"Skipped unnamed place evidence in note {note_index + 1}"
                )
                continue
            grouped[name].append(
                {
                    **evidence,
                    "_source": {
                        "title": note.get("title"),
                        "url": url or None,
                        "published_at": note.get("published_at"),
                        "checked_at": note.get("checked_at"),
                    },
                }
            )

    cards = []
    for name, evidence_items in grouped.items():
        features = _unique(
            feature
            for item in evidence_items
            for feature in _strings(item.get("features"))
        )
        reasons = _unique(
            reason
            for item in evidence_items
            for reason in _strings(item.get("why_visit"))
        )
        caveats = _unique(
            caveat
            for item in evidence_items
            for caveat in _strings(item.get("caveats"))
        )
        best_times = _unique(
            str(item.get("best_time") or "").strip() for item in evidence_items
        )
        physical_loads = _unique(
            str(item.get("physical_load") or "").strip()
            for item in evidence_items
        )
        durations = [
            int(item["suggested_duration_minutes"])
            for item in evidence_items
            if isinstance(item.get("suggested_duration_minutes"), (int, float))
            and int(item["suggested_duration_minutes"]) > 0
        ]
        source_refs = [
            item["_source"]
            for item in evidence_items
            if item["_source"].get("url")
        ]

        missing = []
        if not features:
            missing.append("features")
        if not reasons:
            missing.append("why_visit")
        if not durations:
            missing.append("suggested_duration_minutes")
        if not source_refs:
            missing.append("source_refs")

        cards.append(
            {
                "name": name,
                "features": features,
                "why_visit": reasons,
                "suggested_duration_minutes": (
                    round(sum(durations) / len(durations)) if durations else None
                ),
                "best_time": best_times,
                "physical_load": physical_loads,
                "caveats": caveats,
                "source_refs": source_refs,
                "evidence_count": len(evidence_items),
                "missing_fields": missing,
            }
        )

    cards.sort(
        key=lambda card: (
            bool(card["missing_fields"]),
            -card["evidence_count"],
            card["name"],
        )
    )
    if not cards:
        errors.append("No attraction cards could be compiled")
    incomplete = [card["name"] for card in cards if card["missing_fields"]]
    if incomplete:
        warnings.append(
            "Incomplete attraction cards: " + ", ".join(incomplete)
        )

    return {
        "status": "VALID" if cards and not errors else "INVALID",
        "destination": research.get("destination"),
        "travel_style": research.get("travel_style"),
        "attraction_cards": cards,
        "errors": errors,
        "warnings": warnings,
        "source_note_count": len(notes),
    }


#: Errors a blocked source can legitimately explain.
#:
#: Deliberately only the absence of attractions altogether. A blocked source
#: justifies having nothing to say; it never justifies listing a place and
#: leaving it empty. If nothing could be researched, the place should not be
#: in the plan at all — an attraction with no features, no reason to visit and
#: no source did not come from a blocked lookup, it came from the model.
_EVIDENCE_DEPENDENT_ERRORS = ("Plan has no attraction activities",)


def validate_plan_content(plan: Dict[str, Any]) -> dict:
    """Check that a plan explains what to visit, not only how to travel.

    A plan may also declare `unavailable_sources`. When every source that
    could have supplied attraction content was blocked, the missing content is
    reported as `INCOMPLETE_EVIDENCE` rather than `INVALID`: refusing to
    return anything would be the wrong answer for a traveller who can still
    use the transport research, and "Plan has no attraction activities" reads
    as the author's fault when in fact nothing could be looked up.
    """

    errors: List[str] = []
    warnings: List[str] = []
    days = plan.get("days") or []
    segments = plan.get("segments") or []
    source_index = {
        str(source.get("id"))
        for source in (plan.get("sources") or [])
        if isinstance(source, dict) and source.get("id")
    }

    if not isinstance(days, list) or not days:
        errors.append("Plan has no days")
        days = []

    attraction_count = 0
    activity_ids = []
    for day_index, day in enumerate(days):
        activities = (day.get("activities") or []) if isinstance(day, dict) else []
        if not activities:
            errors.append(f"Day {day_index + 1} has no activities")
            continue
        for activity in activities:
            if not isinstance(activity, dict):
                errors.append(f"Day {day_index + 1} contains an invalid activity")
                continue
            activity_id = str(activity.get("id") or "").strip()
            if activity_id:
                activity_ids.append(activity_id)
            if not str(activity.get("description") or "").strip():
                errors.append(
                    f"Activity {activity_id or activity.get('name')} has no description"
                )
            if str(activity.get("type") or "").upper() != "ATTRACTION":
                continue

            attraction_count += 1
            label = activity_id or str(activity.get("name") or "unknown")
            if not _strings(activity.get("features")):
                errors.append(f"Attraction {label} has no defining features")
            if not _strings(activity.get("why_visit")):
                errors.append(f"Attraction {label} has no reason to visit")
            duration = activity.get("suggested_duration_minutes")
            if not isinstance(duration, (int, float)) or duration <= 0:
                errors.append(f"Attraction {label} has no suggested duration")
            refs = _strings(activity.get("source_refs"))
            if not refs:
                errors.append(f"Attraction {label} has no source refs")
            elif source_index:
                unknown = [ref for ref in refs if ref not in source_index]
                if unknown:
                    warnings.append(
                        f"Attraction {label} references unknown sources: "
                        + ", ".join(unknown)
                    )

    if attraction_count == 0:
        errors.append("Plan has no attraction activities")

    segment_pairs = {
        (str(segment.get("from_id")), str(segment.get("to_id")))
        for segment in segments
        if isinstance(segment, dict)
    }
    for from_id, to_id in zip(activity_ids, activity_ids[1:]):
        if (from_id, to_id) not in segment_pairs:
            errors.append(f"Missing transition segment: {from_id} -> {to_id}")

    # Structural checks only: a stored plan is not necessarily one being
    # presented, so freshness is left to validate-flights, which takes a clock.
    flight_report = validate_offers(plan.get("flight_offers") or [])
    errors.extend(issue["message"] for issue in flight_report["hard_conflicts"])
    warnings.extend(issue["message"] for issue in flight_report["warnings"])

    unavailable = [
        entry
        for entry in (plan.get("unavailable_sources") or [])
        if isinstance(entry, dict) and entry.get("provider")
    ]
    explained, unexplained = [], []
    for message in errors:
        target = explained if (
            unavailable
            and any(marker in message for marker in _EVIDENCE_DEPENDENT_ERRORS)
        ) else unexplained
        target.append(message)

    if unexplained:
        status = "INVALID"
    elif explained:
        status = "INCOMPLETE_EVIDENCE"
    else:
        status = "VALID"

    return {
        "status": status,
        "errors": unexplained,
        "warnings": warnings,
        "unmet_by_blocked_sources": explained,
        "unavailable_sources": unavailable,
        "summary": {
            "day_count": len(days),
            "attraction_count": attraction_count,
            "segment_count": len(segments),
        },
    }
