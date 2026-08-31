"""Unit tests for app.services.repository against in-memory SQLite."""

from __future__ import annotations

import types
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import DeviceStatus
from app.services import repository


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine)
    session = session_local()
    try:
        yield session
    finally:
        session.close()


def _fake_pywemo_device(**overrides):
    defaults = dict(
        udn="uuid:Socket-1_0-12345",
        host="10.0.1.5",
        port=49153,
        name="Kitchen Switch",
        mac="AA:BB:CC:DD:EE:FF",
        manufacturer="Belkin International Inc.",
        model="Socket",
        model_name="Wemo Switch",
        serial_number="221234567890",
        firmware_version="WeMo_WW_2.00.11452.PVT-OWRT-SNS",
    )
    defaults.update(overrides)
    device = types.SimpleNamespace(**defaults)
    device.session = types.SimpleNamespace(url=f"http://{device.host}:{device.port}/setup.xml")
    return device


def test_upsert_creates_new_device(db):
    device = repository.upsert_from_pywemo(db, _fake_pywemo_device())
    assert device.id is not None
    assert device.name == "Kitchen Switch"
    assert device.status == DeviceStatus.ONLINE
    assert len(repository.list_devices(db)) == 1


def test_upsert_updates_existing_device_by_udn(db):
    repository.upsert_from_pywemo(db, _fake_pywemo_device())
    updated = repository.upsert_from_pywemo(
        db, _fake_pywemo_device(name="Kitchen Switch (renamed)", host="10.0.1.9")
    )
    assert len(repository.list_devices(db)) == 1
    assert updated.name == "Kitchen Switch (renamed)"
    assert updated.host == "10.0.1.9"


def test_delete_device_removes_row(db):
    device = repository.upsert_from_pywemo(db, _fake_pywemo_device())
    assert repository.delete_device(db, device.id) is True
    assert repository.get_device(db, device.id) is None


def test_delete_missing_device_returns_false(db):
    assert repository.delete_device(db, 9999) is False


def test_mark_state_offline_sets_error_and_status(db):
    device = repository.upsert_from_pywemo(db, _fake_pywemo_device())
    updated = repository.mark_state(
        db, device, binary_state=None, status=DeviceStatus.OFFLINE, error="timeout"
    )
    assert updated.status == DeviceStatus.OFFLINE
    assert updated.last_error == "timeout"
    assert updated.binary_state is None


def test_mark_state_stores_brightness(db):
    device = repository.upsert_from_pywemo(db, _fake_pywemo_device())
    updated = repository.mark_state(
        db, device, binary_state=1, brightness=42, status=DeviceStatus.ONLINE
    )
    assert updated.brightness == 42


def test_rules_summary_cache_replaces_the_previous_snapshot(db):
    device = repository.upsert_from_pywemo(db, _fake_pywemo_device())
    first = repository.cache_rules_summary(db, device.id, [{"name": "First"}])
    updated = repository.cache_rules_summary(db, device.id, [{"name": "Updated"}])

    assert first.id == updated.id
    assert updated.summary_json == '[{"name": "Updated"}]'
    assert repository.get_cached_rules_summary(db, device.id).id == updated.id


def test_mark_state_emits_only_for_visible_changes(db):
    device = repository.upsert_from_pywemo(db, _fake_pywemo_device())
    with patch.object(repository.device_events, "emit") as emit:
        repository.mark_state(
            db, device, binary_state=None, brightness=None, status=DeviceStatus.ONLINE
        )
        emit.assert_not_called()

        repository.mark_state(
            db, device, binary_state=1, brightness=None, status=DeviceStatus.ONLINE
        )
        emit.assert_called_once()


def test_update_device_name_via_patch_like_flow(db):
    device = repository.upsert_from_pywemo(db, _fake_pywemo_device())
    device.name = "Renamed"
    db.add(device)
    db.commit()
    db.refresh(device)
    fetched = repository.get_device(db, device.id)
    assert fetched.name == "Renamed"
