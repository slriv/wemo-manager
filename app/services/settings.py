"""Wi-Fi credential storage."""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from ..models import Setting

WIFI_SSID = "wifi_ssid"
WIFI_PASSWORD = "wifi_password"


def get_setting(db: Session, key: str) -> str | None:
    row = db.get(Setting, key)
    return row.value if row is not None else None


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
    else:
        row.value = value
    db.add(row)
    db.commit()


def seed_defaults_from_env(db: Session) -> None:
    """Seed Wi-Fi credentials on first run only; never overwrites a saved value."""
    ssid = os.environ.get("WEMO_MANAGER_WIFI_SSID")
    if ssid and get_setting(db, WIFI_SSID) is None:
        set_setting(db, WIFI_SSID, ssid)

    password = os.environ.get("WEMO_MANAGER_WIFI_PASSWORD")
    if password and get_setting(db, WIFI_PASSWORD) is None:
        set_setting(db, WIFI_PASSWORD, password)
