"""Tests for human-readable WeMo rules summaries."""

from app.services.rule_summary import calendar_events, consolidate_rules, summarize_rules


def test_summarize_rules_groups_schedule_rows_and_resolves_devices():
    rules_db = {
        "RULES": [
            {"RuleID": "4", "Name": "Porch", "Type": "Time Interval", "State": "1"}
        ],
        "RULEDEVICES": [
            {
                "RuleID": 4,
                "DeviceID": "uuid:porch",
                "DayID": 2,
                "StartTime": 64800,
                "EndTime": 82800,
                "StartAction": 1.0,
                "EndAction": 0.0,
                "OnModeOffset": -900,
                "OffModeOffset": 0,
            },
            {
                "RuleID": 4,
                "DeviceID": "uuid:porch",
                "DayID": 3,
                "StartTime": 64800,
                "EndTime": 82800,
                "StartAction": 1.0,
                "EndAction": 0.0,
                "OnModeOffset": -900,
                "OffModeOffset": 0,
            },
        ],
    }

    summary = summarize_rules(rules_db, {"uuid:porch": "Front Porch"})

    assert summary == [
        {
            "id": "4",
            "name": "Porch",
            "type": "Time Interval",
            "enabled": True,
            "days": "Mon, Tue",
            "start": {"action": "on", "times": "6:00 PM"},
            "end": {"action": "off", "times": "11:00 PM"},
            "targets": ["Front Porch"],
            "notes": ["Start time randomized up to 15 minutes"],
            "events": [
                {"day": 2, "start_seconds": 64800, "end_seconds": 82800, "start": "6:00 PM", "end": "11:00 PM", "start_action": "on", "end_action": "off"},
                {"day": 3, "start_seconds": 64800, "end_seconds": 82800, "start": "6:00 PM", "end": "11:00 PM", "start_action": "on", "end_action": "off"},
            ],
        }
    ]


def test_summarize_rules_handles_all_days_and_unknown_device_ids():
    rule_rows = [
        {
            "RuleID": "7",
            "DeviceID": "uuid:unknown",
            "DayID": day,
            "StartTime": 0,
            "EndTime": 3600,
            "StartAction": 1,
            "EndAction": 0,
        }
        for day in range(1, 8)
    ]

    summary = summarize_rules(
        {"RULES": [{"RuleID": 7, "State": 0}], "RULEDEVICES": rule_rows}, {}
    )

    assert summary[0]["enabled"] is False
    assert summary[0]["days"] == "Every day"
    assert summary[0]["targets"] == ["uuid:unknown"]


def test_consolidate_rules_merges_replicated_rule_and_keeps_sources():
    rule = {
        "id": "4",
        "name": "Porch",
        "type": "Time Interval",
        "enabled": True,
        "days": "Every day",
        "start": {"action": "on", "times": "6:00 PM"},
        "end": {"action": "off", "times": "11:00 PM"},
        "targets": ["Front Porch"],
        "notes": [],
    }

    consolidated = consolidate_rules([("Kitchen", [rule]), ("Hall", [rule])])

    assert len(consolidated) == 1
    assert consolidated[0]["sources"] == ["Kitchen", "Hall"]


def test_calendar_events_expands_cached_weekday_events():
        events = calendar_events(
                [{"id": "4", "name": "Porch", "type": "Time Interval", "enabled": True,
                    "targets": ["Front Porch"], "events": [{"day": 2, "start_seconds": 64800,
                    "end_seconds": 82800, "start": "6:00 PM", "end": "11:00 PM", "start_action": "on", "end_action": "off"}]}],
                "Basement Lights", "2026-08-31T12:00:00+00:00",
        )
        assert events[0]["day_name"] == "Mon"
        assert events[0]["targets"] == ["Front Porch"]


def test_calendar_events_uses_consolidated_sources_when_present():
        events = calendar_events(
                [{"id": "4", "name": "Porch", "type": "Time Interval", "enabled": True,
                    "targets": [], "sources": ["Kitchen", "Hall"], "events": [{"day": 2,
                    "start_seconds": 0, "end_seconds": 1, "start": "12:00 AM", "end": "12:00 AM",
                    "start_action": "on", "end_action": "off"}]}], "fallback", "now"
        )
        assert events[0]["source"] == "Kitchen, Hall"


def test_calendar_events_omits_duplicate_raw_schedule_rows():
    event = {
        "day": 2,
        "start_seconds": 64800,
        "end_seconds": 82800,
        "start": "6:00 PM",
        "end": "11:00 PM",
        "start_action": "on",
        "end_action": "off",
    }
    events = calendar_events(
        [{"id": "4", "name": "Porch", "type": "Time Interval", "enabled": True,
          "targets": ["Front Porch"], "events": [event, event]}], "source", "now"
    )
    assert len(events) == 1
