"""Tests for schema creation and replacement in app.database."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from app import database


@pytest.fixture
def engine(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'wemo.db'}")
    monkeypatch.setattr(database, "engine", engine)
    return engine


def _settings_rows(engine) -> list[tuple]:
    with engine.begin() as conn:
        return [tuple(row) for row in conn.execute(text("SELECT key, value FROM settings"))]


def test_init_db_creates_the_schema(engine):
    database.init_db()
    assert set(inspect(engine).get_table_names()) >= {"devices", "settings", "device_rules_cache"}


def test_init_db_keeps_data_when_the_schema_matches(engine):
    database.init_db()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO settings (key, value) VALUES ('wifi_ssid', 'HomeNet')"))

    database.init_db()

    assert _settings_rows(engine) == [("wifi_ssid", "HomeNet")]


def test_init_db_replaces_the_database_when_a_table_has_an_extra_column(engine):
    database.init_db()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO settings (key, value) VALUES ('wifi_ssid', 'HomeNet')"))
        conn.execute(text("ALTER TABLE settings ADD COLUMN stale TEXT"))

    database.init_db()

    assert {c["name"] for c in inspect(engine).get_columns("settings")} == {"key", "value"}
    assert _settings_rows(engine) == []


def test_init_db_replaces_every_table_not_just_the_stale_one(engine):
    database.init_db()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO settings (key, value) VALUES ('wifi_ssid', 'HomeNet')"))
        conn.execute(text("ALTER TABLE devices ADD COLUMN stale TEXT"))

    database.init_db()

    assert _settings_rows(engine) == []
