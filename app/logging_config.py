"""Application logging configuration."""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "wemo_manager.log"

LOG_FILE = Path(os.environ.get("WEMO_MANAGER_LOG_FILE", str(DEFAULT_LOG_FILE)))
FILE_LOG_LEVEL = os.environ.get("WEMO_MANAGER_FILE_LOG_LEVEL", "INFO").upper()
CONSOLE_LOG_LEVEL = os.environ.get("WEMO_MANAGER_CONSOLE_LOG_LEVEL", "WARNING").upper()
MAX_BYTES = int(os.environ.get("WEMO_MANAGER_LOG_MAX_BYTES", 5 * 1024 * 1024))  # 5 MiB
BACKUP_COUNT = int(os.environ.get("WEMO_MANAGER_LOG_BACKUP_COUNT", 5))

_configured = False


def configure_logging() -> None:
    global _configured  # noqa: PLW0603
    if _configured:
        return
    _configured = True

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    )

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
    )
    file_handler.setLevel(FILE_LOG_LEVEL)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(CONSOLE_LOG_LEVEL)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(min(file_handler.level, console_handler.level))
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Route Uvicorn logs through application handlers.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(logger_name)
        uv_logger.handlers.clear()
        uv_logger.addHandler(file_handler)
        uv_logger.addHandler(console_handler)
        uv_logger.propagate = False

    logging.getLogger(__name__).info(
        "Logging configured: file=%s (level=%s), console level=%s",
        LOG_FILE,
        FILE_LOG_LEVEL,
        CONSOLE_LOG_LEVEL,
    )
