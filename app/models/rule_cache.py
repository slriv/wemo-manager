"""Persisted, read-only cache of schedules fetched from WeMo devices."""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class DeviceRulesCache(Base):
    """Availability cache only; rules remain authoritative on the physical device."""

    __tablename__ = "device_rules_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    summary_json: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)
