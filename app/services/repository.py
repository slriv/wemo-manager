"""Repository/CRUD helpers for the Device table."""

from __future__ import annotations

import datetime
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Device, DeviceRulesCache, DeviceStatus
from .events import device_events


def list_devices(db: Session) -> list[Device]:
    return list(db.scalars(select(Device).order_by(Device.name)))


def get_device(db: Session, device_id: int) -> Device | None:
    return db.get(Device, device_id)


def get_device_by_udn(db: Session, udn: str) -> Device | None:
    return db.scalars(select(Device).where(Device.udn == udn)).first()


def upsert_from_pywemo(db: Session, pywemo_device) -> Device:
    existing = get_device_by_udn(db, pywemo_device.udn)
    now = datetime.datetime.now(datetime.UTC)

    fields = {
        "host": pywemo_device.host,
        "port": pywemo_device.port,
        "setup_url": pywemo_device.session.url,
        "name": pywemo_device.name,
        "mac": pywemo_device.mac,
        "manufacturer": pywemo_device.manufacturer,
        "model": pywemo_device.model,
        "model_name": pywemo_device.model_name,
        "serial_number": pywemo_device.serial_number,
        "firmware_version": pywemo_device.firmware_version,
        "device_type": type(pywemo_device).__name__,
        "status": DeviceStatus.ONLINE,
        "last_seen_at": now,
        "last_error": None,
    }

    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        device_events.emit()
        return existing

    device = Device(udn=pywemo_device.udn, **fields)
    db.add(device)
    db.commit()
    db.refresh(device)
    device_events.emit()
    return device


def delete_device(db: Session, device_id: int) -> bool:
    """Return True if a row was deleted."""
    device = get_device(db, device_id)
    if device is None:
        return False
    cached_rules = db.scalars(
        select(DeviceRulesCache).where(DeviceRulesCache.device_id == device_id)
    ).first()
    if cached_rules is not None:
        db.delete(cached_rules)
    db.delete(device)
    db.commit()
    device_events.emit()
    return True


def cache_rules_summary(db: Session, device_id: int, summary: list[dict]) -> DeviceRulesCache:
    cached = db.scalars(
        select(DeviceRulesCache).where(DeviceRulesCache.device_id == device_id)
    ).first()
    if cached is None:
        cached = DeviceRulesCache(device_id=device_id, summary_json="[]")
    cached.summary_json = json.dumps(summary)
    cached.fetched_at = datetime.datetime.now(datetime.UTC)
    db.add(cached)
    db.commit()
    db.refresh(cached)
    return cached


def get_cached_rules_summary(db: Session, device_id: int) -> DeviceRulesCache | None:
    return db.scalars(
        select(DeviceRulesCache).where(DeviceRulesCache.device_id == device_id)
    ).first()


def mark_state(
    db: Session,
    device: Device,
    *,
    binary_state: int | None,
    status: DeviceStatus,
    brightness: int | None = None,
    error: str | None = None,
) -> Device:
    """Update a device's last-known state after a poll or push event."""
    changed = (
        device.binary_state != binary_state
        or device.brightness != brightness
        or device.status != status
        or device.last_error != error
    )
    device.binary_state = binary_state
    device.brightness = brightness
    device.status = status
    device.last_error = error
    if status == DeviceStatus.ONLINE:
        device.last_seen_at = datetime.datetime.now(datetime.UTC)
    db.add(device)
    db.commit()
    db.refresh(device)
    if changed:
        device_events.emit()
    return device
