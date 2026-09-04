"""Tests for the settings service and the setup API."""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services import settings

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import get_db  # noqa: E402
from app.routers import setup  # noqa: E402


@pytest.fixture
def db():
    # StaticPool: TestClient uses a worker thread, and each :memory: connection is separate.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(setup.router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_settings_roundtrip(db):
    assert settings.get_setting(db, settings.WIFI_SSID) is None
    settings.set_setting(db, settings.WIFI_SSID, "HomeNet")
    assert settings.get_setting(db, settings.WIFI_SSID) == "HomeNet"
    settings.set_setting(db, settings.WIFI_SSID, "OtherNet")
    assert settings.get_setting(db, settings.WIFI_SSID) == "OtherNet"


def test_seed_defaults_from_env_sets_unconfigured_values(db, monkeypatch):
    monkeypatch.setenv("WEMO_MANAGER_WIFI_SSID", "SeededNet")
    monkeypatch.setenv("WEMO_MANAGER_WIFI_PASSWORD", "seeded-password")
    settings.seed_defaults_from_env(db)
    assert settings.get_setting(db, settings.WIFI_SSID) == "SeededNet"
    assert settings.get_setting(db, settings.WIFI_PASSWORD) == "seeded-password"


def test_seed_defaults_from_env_does_not_overwrite_existing(db, monkeypatch):
    settings.set_setting(db, settings.WIFI_SSID, "AlreadySet")
    monkeypatch.setenv("WEMO_MANAGER_WIFI_SSID", "SeededNet")
    settings.seed_defaults_from_env(db)
    assert settings.get_setting(db, settings.WIFI_SSID) == "AlreadySet"


def test_seed_defaults_from_env_noop_when_unset(db, monkeypatch):
    monkeypatch.delenv("WEMO_MANAGER_WIFI_SSID", raising=False)
    monkeypatch.delenv("WEMO_MANAGER_WIFI_PASSWORD", raising=False)
    settings.seed_defaults_from_env(db)
    assert settings.get_setting(db, settings.WIFI_SSID) is None
    assert settings.get_setting(db, settings.WIFI_PASSWORD) is None


def test_config_returns_stored_credentials(client):
    config = client.get("/api/setup/config").json()
    assert config == {
        "wifi_ssid": "",
        "wifi_password": "",
        "apk_available": setup.APK_PATH.is_file(),
        "server_host": "",
    }

    config = client.put(
        "/api/setup/config",
        json={"wifi_ssid": "HomeNet", "wifi_password": "hunter22"},
    ).json()
    assert config["wifi_ssid"] == "HomeNet"
    assert config["wifi_password"] == "hunter22"


def test_config_partial_update_keeps_other_fields(client):
    client.put(
        "/api/setup/config",
        json={"wifi_ssid": "HomeNet", "wifi_password": "hunter22"},
    )
    config = client.put("/api/setup/config", json={"wifi_ssid": "NewNet"}).json()
    assert config["wifi_ssid"] == "NewNet"
    assert config["wifi_password"] == "hunter22"


def test_upload_logs_writes_to_logger(client, caplog):
    with caplog.at_level("INFO", logger="mobile_wizard"):
        response = client.post("/api/setup/logs", json={"text": "wizard diagnostic line"})
    assert response.json() == {"status": "ok"}
    assert "wizard diagnostic line" in caplog.text


def test_apk_path_honors_env_override(monkeypatch, tmp_path):
    override = tmp_path / "wemo-manager.apk"
    monkeypatch.setenv("WEMO_MANAGER_APK_PATH", str(override))
    try:
        reloaded = importlib.reload(setup)
        assert reloaded.APK_PATH == override
    finally:
        importlib.reload(setup)
