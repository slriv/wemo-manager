"""Manage live devices, subscriptions, and polling."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

import pywemo
from pywemo.discovery import device_from_description
from pywemo.exceptions import PyWeMoException

from ..database import SessionLocal
from ..models import DeviceStatus
from . import repository

LOG = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 60.0


def _get_brightness(device: pywemo.WeMoDevice) -> int | None:
    """Return a dimmer's brightness (1-100), or None for non-dimmable devices."""
    if not hasattr(device, "get_brightness"):
        return None
    try:
        return device.get_brightness(force_update=False)
    except PyWeMoException:
        return None


class DeviceManager:
    """Owns live pywemo Device objects and keeps the database in sync with them."""

    def __init__(self, poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS) -> None:
        self.poll_interval = poll_interval
        self._live_devices: dict[str, pywemo.WeMoDevice] = {}
        self._lock = threading.Lock()
        self.registry = pywemo.SubscriptionRegistry()
        self._poll_task: asyncio.Task[None] | None = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self.registry.start()
        self._started = True

    def stop(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
        if self._started:
            self.registry.stop()
            self._started = False

    async def start_poll_loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.poll_all)
            except Exception:  # pragma: no cover
                LOG.exception("Unhandled error during device poll loop")
            await asyncio.sleep(self.poll_interval)

    def _load_known_devices(self) -> None:
        with SessionLocal() as db:
            for row in repository.list_devices(db):
                self._connect(row.udn, row.setup_url)

    def _connect(self, udn: str, setup_url: str) -> pywemo.WeMoDevice | None:
        try:
            device = device_from_description(setup_url)
        except PyWeMoException:
            LOG.exception("Failed to connect to device at %s", setup_url)
            return None

        if device is None or device.udn != udn:
            LOG.warning(
                "Device at %s did not match expected udn %s", setup_url, udn
            )
            return None

        with self._lock:
            self._live_devices[udn] = device

        try:
            self.registry.register(device)
            self.registry.on(device, None, self._make_push_callback(udn))
        except PyWeMoException:  # pragma: no cover
            LOG.exception("Failed to register push subscription for %s", udn)

        return device

    def get_live_device(self, udn: str) -> pywemo.WeMoDevice | None:
        with self._lock:
            return self._live_devices.get(udn)

    def register_new_device(self, device: pywemo.WeMoDevice) -> None:
        with self._lock:
            self._live_devices[device.udn] = device
        try:
            self.registry.register(device)
            self.registry.on(device, None, self._make_push_callback(device.udn))
        except PyWeMoException:  # pragma: no cover
            LOG.exception("Failed to register push subscription for %s", device.udn)

    def forget_device(self, udn: str) -> None:
        with self._lock:
            device = self._live_devices.pop(udn, None)
        if device is not None:
            try:
                self.registry.unregister(device)
            except PyWeMoException:  # pragma: no cover
                LOG.exception("Failed to unregister push subscription for %s", udn)

    def _make_push_callback(self, udn: str):
        def _callback(device: pywemo.WeMoDevice, event_type: str, params: Any) -> None:
            LOG.debug("Push event for %s: %s %r", udn, event_type, params)
            try:
                device.subscription_update(event_type, params)
                state = device.get_state(force_update=False)
            except PyWeMoException:
                LOG.exception("Failed to process push event for %s", udn)
                return
            with SessionLocal() as db:
                row = repository.get_device_by_udn(db, udn)
                if row is not None:
                    repository.mark_state(
                        db,
                        row,
                        binary_state=state,
                        brightness=_get_brightness(device),
                        status=DeviceStatus.ONLINE,
                    )

        return _callback

    def poll_all(self) -> None:
        """Refresh state for every known device. Blocking; runs in a worker thread."""
        with SessionLocal() as db:
            rows = repository.list_devices(db)
            for row in rows:
                device = self.get_live_device(row.udn) or self._connect(
                    row.udn, row.setup_url
                )
                if device is None:
                    repository.mark_state(
                        db,
                        row,
                        binary_state=None,
                        status=DeviceStatus.OFFLINE,
                        error="Unable to connect to device",
                    )
                    continue
                try:
                    state = device.get_state(force_update=True)
                except PyWeMoException as err:
                    LOG.info("Poll failed for %s (%s): %r", row.name, row.host, err)
                    repository.mark_state(
                        db, row, binary_state=None, status=DeviceStatus.OFFLINE, error=str(err)
                    )
                else:
                    repository.mark_state(
                        db,
                        row,
                        binary_state=state,
                        brightness=_get_brightness(device),
                        status=DeviceStatus.ONLINE,
                    )

    def set_device_state(
        self, udn: str, *, on: bool | None = None, level: int | None = None
    ) -> tuple[int, int | None]:
        """Set state or brightness and return the resulting state."""
        device = self.get_live_device(udn)
        if device is None:
            raise PyWeMoException(f"Device {udn} is not connected")
        if level is not None:
            if not hasattr(device, "set_brightness"):
                raise PyWeMoException(f"Device {udn} does not support brightness")
            device.set_brightness(level)
        elif on is not None:
            device.set_state(1 if on else 0)
        return device.get_state(force_update=True), _get_brightness(device)

    def reset_device(self, udn: str, *, data: bool, wifi: bool) -> str:
        """Reset device data and optionally Wi-Fi credentials."""
        device = self.get_live_device(udn)
        if device is None:
            raise PyWeMoException(f"Device {udn} is not connected")
        return device.reset(data=data, wifi=wifi)


device_manager = DeviceManager()
