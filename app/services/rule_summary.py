"""Convert WeMo's raw on-device rules database into display-ready summaries."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
import json
from typing import Any

DAY_NAMES = {
    1: "Sun",
    2: "Mon",
    3: "Tue",
    4: "Wed",
    5: "Thu",
    6: "Fri",
    7: "Sat",
}


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _time_of_day(seconds: Any) -> str | None:
    seconds = _as_int(seconds)
    if seconds is None or not 0 <= seconds < 24 * 60 * 60:
        return None
    hour, remainder = divmod(seconds, 60 * 60)
    minute = remainder // 60
    suffix = "AM" if hour < 12 else "PM"
    hour = hour % 12 or 12
    return f"{hour}:{minute:02d} {suffix}"


def _time_range(rows: Iterable[dict[str, Any]], field: str) -> str:
    values = sorted(
        value
        for row in rows
        if (value := _as_int(row.get(field))) is not None and 0 <= value < 24 * 60 * 60
    )
    if not values:
        return "Unknown"
    start = _time_of_day(values[0])
    end = _time_of_day(values[-1])
    return start if start == end else f"{start}–{end}"


def _days(rows: Iterable[dict[str, Any]]) -> str:
    values = sorted({_as_int(row.get("DayID")) for row in rows} - {None})
    if values == list(DAY_NAMES):
        return "Every day"
    return ", ".join(DAY_NAMES.get(day, f"Day {day}") for day in values) or "No days"


def _action(value: Any) -> str:
    if value == 1 or value == 1.0 or value == "1" or value == "1.0":
        return "on"
    if value == 0 or value == 0.0 or value == "0" or value == "0.0":
        return "off"
    return "set state"


def _randomization(values: set[int], label: str) -> str | None:
    offsets = {abs(value) for value in values if value}
    if not offsets:
        return None
    seconds = max(offsets)
    minutes = seconds // 60
    amount = f"{minutes} minute{'s' if minutes != 1 else ''}" if minutes else f"{seconds} seconds"
    return f"{label} time randomized up to {amount}"


def summarize_rules(
    rules_db: dict[str, list[dict[str, Any]]], device_names: dict[str, str]
) -> list[dict[str, Any]]:
    """Summarize ``RULES`` joined to ``RULEDEVICES`` on ``RuleID``, omitting unknown fields."""
    rows_by_rule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rules_db.get("RULEDEVICES", []):
        rule_id = row.get("RuleID")
        if rule_id is not None:
            rows_by_rule[str(rule_id)].append(row)

    summaries = []
    for rule in rules_db.get("RULES", []):
        rule_id = str(rule.get("RuleID"))
        rows = rows_by_rule[rule_id]
        device_ids = list(dict.fromkeys(str(row["DeviceID"]) for row in rows if row.get("DeviceID")))
        targets = [device_names.get(device_id, device_id) for device_id in device_ids]
        starts = _time_range(rows, "StartTime")
        ends = _time_range(rows, "EndTime")
        start_action = _action(rows[0].get("StartAction")) if rows else "set state"
        end_action = _action(rows[0].get("EndAction")) if rows else "set state"
        on_offsets = {_as_int(row.get("OnModeOffset")) for row in rows} - {None}
        off_offsets = {_as_int(row.get("OffModeOffset")) for row in rows} - {None}
        notes = [
            note
            for note in (
                _randomization(on_offsets, "Start"),
                _randomization(off_offsets, "End"),
            )
            if note
        ]
        state = str(rule.get("State", ""))
        summaries.append(
            {
                "id": rule_id,
                "name": rule.get("Name") or f"Rule {rule_id}",
                "type": rule.get("Type") or "Unknown",
                "enabled": state == "1",
                "days": _days(rows),
                "start": {"action": start_action, "times": starts},
                "end": {"action": end_action, "times": ends},
                "targets": targets,
                "notes": notes,
                "events": [
                    {
                        "day": _as_int(row.get("DayID")),
                        "start_seconds": _as_int(row.get("StartTime")),
                        "end_seconds": _as_int(row.get("EndTime")),
                        "start": _time_of_day(row.get("StartTime")),
                        "end": _time_of_day(row.get("EndTime")),
                        "start_action": _action(row.get("StartAction")),
                        "end_action": _action(row.get("EndAction")),
                    }
                    for row in rows
                ],
            }
        )
    return summaries


def consolidate_rules(
    summaries_by_device: Iterable[tuple[str, list[dict[str, Any]]]]
) -> list[dict[str, Any]]:
    """Merge identical replicated rules, retaining the devices that supplied them."""
    consolidated: dict[str, dict[str, Any]] = {}
    for device_name, summaries in summaries_by_device:
        for summary in summaries:
            key_fields = {key: value for key, value in summary.items() if key != "id"}
            key = json.dumps(key_fields, sort_keys=True)
            item = consolidated.setdefault(key, {**summary, "sources": []})
            if device_name not in item["sources"]:
                item["sources"].append(device_name)
    return sorted(consolidated.values(), key=lambda rule: rule["name"].casefold())


def calendar_events(
    summaries: list[dict[str, Any]], source: str, fetched_at: str
) -> list[dict[str, Any]]:
    """Expand rule summaries to one event per stored weekday row."""
    events = []
    seen = set()
    for rule in summaries:
        for index, event in enumerate(rule.get("events", [])):
            day = event.get("day")
            start_seconds = event.get("start_seconds")
            if day not in DAY_NAMES or start_seconds is None:
                continue
            identity = (
                rule["name"],
                rule["type"],
                rule["enabled"],
                day,
                start_seconds,
                event.get("end_seconds"),
                event.get("start_action"),
                event.get("end_action"),
                tuple(rule["targets"]),
            )
            if identity in seen:
                continue
            seen.add(identity)
            events.append(
                {
                    "key": f"{source}:{rule['id']}:{index}",
                    "rule_name": rule["name"],
                    "rule_type": rule["type"],
                    "enabled": rule["enabled"],
                    "day": day,
                    "day_name": DAY_NAMES[day],
                    "start_seconds": start_seconds,
                    "end_seconds": event.get("end_seconds"),
                    "start": event.get("start"),
                    "end": event.get("end"),
                    "start_action": event.get("start_action"),
                    "end_action": event.get("end_action"),
                    "targets": rule["targets"],
                    "source": ", ".join(rule.get("sources", [source])),
                    "fetched_at": fetched_at,
                }
            )
    return events
