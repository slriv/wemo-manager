"""SQLAlchemy ORM models for known WeMo devices."""

from __future__ import annotations

import datetime
import enum

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class DeviceStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    udn: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    host: Mapped[str] = mapped_column(String(64), index=True)
    port: Mapped[int] = mapped_column(Integer)
    setup_url: Mapped[str] = mapped_column(String(255))

    name: Mapped[str] = mapped_column(String(255))
    mac: Mapped[str] = mapped_column(String(32), default="")
    manufacturer: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    model_name: Mapped[str] = mapped_column(String(128), default="")
    serial_number: Mapped[str] = mapped_column(String(64), default="")
    firmware_version: Mapped[str] = mapped_column(String(64), default="")
    device_type: Mapped[str] = mapped_column(String(64), default="")

    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus), default=DeviceStatus.UNKNOWN
    )
    binary_state: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brightness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seen_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Device id={self.id} name={self.name!r} host={self.host}>"
