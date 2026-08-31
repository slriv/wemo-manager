"""Tests for app.logging_config."""

from __future__ import annotations

import importlib
import logging

import app.logging_config as logging_config


def _reset():
    logging_config._configured = False  # pylint: disable=protected-access
    logging.getLogger().handlers.clear()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers.clear()


def test_configure_logging_attaches_file_and_console_handlers(tmp_path, monkeypatch):
    monkeypatch.setenv("WEMO_MANAGER_LOG_FILE", str(tmp_path / "test.log"))
    importlib.reload(logging_config)
    _reset()

    logging_config.configure_logging()

    root = logging.getLogger()
    assert len(root.handlers) == 2
    assert (tmp_path / "test.log").exists()


def test_configure_logging_attaches_to_uvicorn_loggers(tmp_path, monkeypatch):
    monkeypatch.setenv("WEMO_MANAGER_LOG_FILE", str(tmp_path / "test.log"))
    importlib.reload(logging_config)
    _reset()

    logging_config.configure_logging()

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        assert len(uv_logger.handlers) == 2
        assert uv_logger.propagate is False


def test_configure_logging_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("WEMO_MANAGER_LOG_FILE", str(tmp_path / "test.log"))
    importlib.reload(logging_config)
    _reset()

    logging_config.configure_logging()
    logging_config.configure_logging()

    # A second call should not add duplicate handlers.
    assert len(logging.getLogger().handlers) == 2
