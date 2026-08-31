"""Database engine/session setup (SQLite via SQLAlchemy)."""

from __future__ import annotations

import logging
import os
from collections.abc import Generator

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

LOG = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "WEMO_MANAGER_DATABASE_URL", "sqlite:///./wemo_manager.db"
)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create the schema, discarding the whole database first if it does not match."""
    from . import models  # noqa: F401  pylint: disable=import-outside-toplevel,unused-import

    stale = _stale_tables()
    if stale:
        LOG.warning("Schema mismatch in %s; recreating the database", ", ".join(stale))
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _stale_tables() -> list[str]:
    """Existing tables whose columns differ from their model."""
    inspector = inspect(engine)
    stale = []
    for table in Base.metadata.tables.values():
        if not inspector.has_table(table.name):
            continue
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        if existing != {column.name for column in table.columns}:
            stale.append(table.name)
    return stale
