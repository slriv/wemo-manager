"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .database import SessionLocal, init_db
from .logging_config import configure_logging
from .routers import devices, setup, ui
from .services.device_manager import device_manager
from .services.events import device_events
from .services.settings import seed_defaults_from_env

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOCK_FILE = Path(os.environ.get("WEMO_MANAGER_LOCK_FILE", "wemo_manager.lock"))

configure_logging()
LOG = logging.getLogger(__name__)

_lock_fd: int | None = None


def _acquire_singleton_lock() -> None:
    """Two DeviceManagers racing GENA SUBSCRIBEs corrupt device subscription state."""
    global _lock_fd
    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        holder = os.read(fd, 32).decode().strip() or "unknown"
        os.close(fd)
        raise RuntimeError(
            f"Another wemo-manager instance (pid {holder}) already holds "
            f"{LOCK_FILE} — refusing to start a second instance against the same "
            "devices."
        ) from None
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    _lock_fd = fd


def _release_singleton_lock() -> None:
    global _lock_fd
    if _lock_fd is not None:
        fcntl.flock(_lock_fd, fcntl.LOCK_UN)
        os.close(_lock_fd)
        _lock_fd = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    _acquire_singleton_lock()
    init_db()
    with SessionLocal() as db:
        seed_defaults_from_env(db)
    device_events.bind_loop(asyncio.get_running_loop())
    device_manager.start()
    poll_task = asyncio.create_task(device_manager.start_poll_loop())
    try:
        yield
    finally:
        poll_task.cancel()
        device_manager.stop()
        _release_singleton_lock()


app = FastAPI(title="WeMo Manager", lifespan=lifespan)

app.include_router(devices.router)
app.include_router(setup.router)
app.include_router(ui.router)

# Scoped to /static: gzip buffers streaming responses, which would stall the SSE feed.
app.mount(
    "/static",
    GZipMiddleware(StaticFiles(directory=str(STATIC_DIR)), minimum_size=1024),
    name="static",
)
