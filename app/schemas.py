"""Pydantic request/response schemas for the device API."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from .models import DeviceStatus


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    udn: str
    host: str
    port: int
    setup_url: str
    name: str
    mac: str
    manufacturer: str
    model: str
    model_name: str
    serial_number: str
    firmware_version: str
    device_type: str
    image_url: str | None
    status: DeviceStatus
    binary_state: int | None
    brightness: int | None
    last_seen_at: datetime.datetime | None
    last_error: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class DeviceUpdate(BaseModel):
    name: str | None = None


class DetectRequest(BaseModel):
    target: str
    """A CIDR (e.g. "192.168.1.0/24") or a single IP address."""

    timeout: float = 2.0

    persist: bool = False
    """Upsert results immediately instead of holding them for detect/commit."""


class DetectedDevice(BaseModel):
    udn: str
    host: str
    port: int
    setup_url: str
    name: str
    mac: str
    manufacturer: str
    model: str
    model_name: str
    serial_number: str
    firmware_version: str
    device_type: str


class DetectResponse(BaseModel):
    target: str
    devices: list[DetectedDevice]
    persisted: bool


class CommitDetectRequest(BaseModel):
    udns: list[str]
    """UDNs from a prior detect response."""


class SetStateRequest(BaseModel):
    """``level`` (1-100) applies to dimmers and implies on; use ``on=False`` to turn off."""

    on: bool | None = None
    level: int | None = None

    @model_validator(mode="after")
    def _require_one(self) -> "SetStateRequest":
        if self.on is None and self.level is None:
            raise ValueError("Provide at least one of 'on' or 'level'")
        return self


class AllOffRequest(BaseModel):
    device_ids: list[int] | None = None
    """Omit to turn off every known device."""


class ResetRequest(BaseModel):
    data: bool
    """Clear name, icon, and on-device rules/schedules."""

    wifi: bool
    """Clear WiFi credentials — the device drops off this network immediately."""


class SetupConfigRead(BaseModel):
    wifi_ssid: str
    wifi_password: str
    apk_available: bool
    server_host: str = ""
    """This manager's IPv4 address on the caller's subnet, so clients can drop DNS."""


class SetupConfigUpdate(BaseModel):
    """Omitted fields are left unchanged."""

    wifi_ssid: str | None = None
    wifi_password: str | None = None


class SetupLogUpload(BaseModel):
    text: str
